"""The service: it keeps the replay buffer running and saves clips. `spark-clips --daemon`,
started by the systemd user unit. The window and the command line only talk to it over the
control socket (ipc.py).

States: off (the buffer is turned off), waiting (on, but no game is running), starting,
recording, needs_setup (the screen has never been picked: the share dialog must be answered
once, from the window), error (the pipeline would not run; `problem` says why).

Nothing here draws or asks questions: the answers go out as keys the window and the
command line turn into sentences in their own language."""

import fcntl
import os
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import APP_ID, VERSION, buffer, clipfile, games, pipeline
from .core import (buffer_dir, cache_dir, clean_name, clips_dir, fake, load_portal,
                   load_settings, log, runtime_dir, save_portal, save_settings, stamp,
                   state_dir, unique_path)
from .ipc import Server
from .text import t

def _die_with_parent() -> None:
    """Runs in the pipeline's process before it starts: if this program is killed, Linux sends
    the pipeline SIGKILL, so a killed self-test or service never leaves a recorder behind."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGKILL)       # PR_SET_PDEATHSIG
    except Exception:                                    # noqa: BLE001 - not Linux: skip it
        pass


GRACE = 20             # seconds a game may be gone before the buffer stops (alt-tab, a launcher)
TICK = 1.0
GAME_EVERY = 3.0
GAMEMODE_EVERY = 9.0
EARLY_EXIT = 5.0        # a pipeline that dies this fast counts as a failure
MAX_FAILURES = 3
STOP_WAIT = 6.0
RESTART_KEYS = ('codec', 'fps', 'bitrate', 'size', 'sound', 'mic')


class Service:
    def __init__(self, notifier=None, probe: Optional[Callable[[], Optional[games.Game]]] = None,
                 opener: Optional[Callable[[str], None]] = None, folder: Optional[str] = None,
                 sock_path: Optional[str] = None):
        self.lock = threading.RLock()
        self.settings = load_settings()
        self.notifier = notifier
        self.probe = probe or games.current_game
        self.opener = opener or self._xdg_open
        self.folder = folder or buffer_dir()
        self.state = 'off' if not self.settings['keep'] else 'waiting'
        self.problem: Optional[str] = None
        self.detail = ''
        self.game: Optional[games.Game] = None
        self.gone_since: Optional[float] = None
        self.last_probe = 0.0
        self.proc: Optional[subprocess.Popen] = None
        self.portal = None
        self.fd: Optional[int] = None
        self.started_at = 0.0
        self.running_key: tuple = ()
        self.enc: Optional[pipeline.Encoder] = None
        self.failures = 0
        self.retry_at = 0.0
        self.begin_thread: Optional[threading.Thread] = None
        self.saving = 0
        self.last_clip: Optional[Dict[str, Any]] = None
        self.notes: Dict[int, str] = {}
        self.stop_event = threading.Event()
        self.server = Server(self.handle, sock_path)
        self.tick_thread: Optional[threading.Thread] = None
        self.lock_fd: Optional[int] = None
        if self.notifier is not None:
            self.notifier.on_action = self._note_action
        self._gm_pids: List[int] = []
        self._gm_at = 0.0

    # ─── The pipeline ───

    def _clear_problem(self) -> None:
        self.problem, self.detail = None, ''

    def _fail(self, problem: str, detail: str = '') -> None:
        self.problem, self.detail = problem, detail
        self.state = 'error'
        log.warning("problem: %s %s", problem, detail)

    def _begin(self, interactive: bool) -> None:
        """Choose the encoder, check memory, then get the picture source."""
        s = self.settings
        missing = pipeline.missing_elements()
        if missing:
            return self._fail('missing', ', '.join(missing))
        enc = pipeline.pick_encoder(s['codec'], forced=os.environ.get('SPARK_CLIPS_ENCODER'))
        if enc is None:
            return self._fail('no_hevc' if s['codec'] == 'hevc' else 'no_encoder')
        estimate = buffer.estimate_bytes(s['seconds'], s['bitrate'], self._audio_tracks())
        if buffer.too_big(estimate, buffer.free_bytes(self.folder)):
            return self._fail('ram', f"{estimate // 1_000_000}")
        self.enc = enc
        if fake():
            self._launch(pipeline.fake_source(s), 640, 360, None)
            return
        token = load_portal().get('restore_token')
        if not token and not interactive:
            self.state = 'needs_setup'
            return
        self.state = 'starting'
        self.begin_thread = threading.Thread(target=self._portal_worker,
                                             args=(token,), daemon=True, name='clips-portal')
        self.begin_thread.start()

    def _audio_tracks(self) -> int:
        return int(self.settings['sound']) + int(self.settings['mic'])

    def _portal_worker(self, token: Optional[str]) -> None:
        from .portal import PortalCancelled, PortalError, ScreenCastPortal
        portal = None
        try:
            portal = ScreenCastPortal()
            stream = portal.start(token)
        except PortalCancelled:
            with self.lock:
                self.state = 'needs_setup'
            self._close_portal(portal)
            return
        except PortalError as exc:
            with self.lock:
                self._fail('portal', str(exc))
            self._close_portal(portal)
            return
        except Exception as exc:                   # noqa: BLE001
            with self.lock:
                self._fail('portal', str(exc))
            self._close_portal(portal)
            return
        with self.lock:
            if stream.restore_token:
                keep = load_portal()
                keep['restore_token'] = stream.restore_token
                keep['size'] = list(stream.props.get('size') or [])
                save_portal(keep)
            if self.state != 'starting':           # turned off while the dialog was open
                self._close_portal(portal)
                return
            self.portal = portal
            size = stream.props.get('size') or (0, 0)
            self._launch(pipeline.portal_source(stream.fd, stream.node), int(size[0]),
                         int(size[1]), stream.fd)

    @staticmethod
    def _close_portal(portal) -> None:
        if portal is not None:
            try:
                portal.close()
            except Exception:                      # noqa: BLE001
                pass

    def _launch(self, source: List[str], width: int, height: int, fd: Optional[int]) -> None:
        s = self.settings
        os.makedirs(self.folder, mode=0o700, exist_ok=True)
        buffer.clear(self.folder)
        args = pipeline.build(s, self.enc, source, width, height, pipeline.pick_audio_encoder(),
                              self.folder)
        tool = pipeline.gst_tool('gst-launch-1.0')
        if not tool:
            return self._fail('missing', 'gst-launch-1.0')
        log_path = os.path.join(state_dir(), 'gst.log')
        try:
            err = open(log_path, 'wb')
        except OSError:
            err = subprocess.DEVNULL
        try:
            self.proc = subprocess.Popen([tool, *args], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=err,
                                         pass_fds=(fd,) if fd is not None else (),
                                         start_new_session=True, preexec_fn=_die_with_parent)
        except OSError as exc:
            return self._fail('pipeline', str(exc))
        finally:
            if err is not subprocess.DEVNULL:
                err.close()
        self.fd = fd
        self.started_at = time.monotonic()
        self.running_key = tuple(s[k] for k in RESTART_KEYS)
        self.state = 'starting'
        log.info("recording with %s: %s", self.enc.label, ' '.join(args))

    def _gst_tail(self) -> str:
        try:
            with open(os.path.join(state_dir(), 'gst.log'), 'rb') as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 600))
                return f.read().decode('utf-8', 'replace').strip().splitlines()[-1][:200]
        except (OSError, IndexError):
            return ''

    def _stop_pipeline(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(STOP_WAIT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        self._close_portal(self.portal)
        self.portal = None
        self.started_at = 0.0
        if not self.saving:
            buffer.clear(self.folder)

    def _exited(self) -> None:
        """The pipeline ended by itself."""
        code = self.proc.returncode if self.proc else None
        quick = time.monotonic() - self.started_at < EARLY_EXIT
        detail = self._gst_tail()
        self.proc = None
        self._stop_pipeline()
        self.failures = self.failures + 1 if quick or code else 0
        log.warning("the pipeline ended (code %s, %s s): %s", code,
                    int(time.monotonic() - self.started_at), detail)
        if self.failures >= MAX_FAILURES:
            self._fail('pipeline', detail)
        else:
            self.state = 'waiting'
            self.retry_at = time.monotonic() + 2 ** max(1, self.failures)

    # ─── Watching ───

    def _watch_games(self, now: float) -> None:
        if now - self.last_probe < GAME_EVERY and self.last_probe:
            return
        self.last_probe = now
        try:
            found = self.probe()
        except Exception:                          # noqa: BLE001 - never stop on a probe error
            log.exception("game detection failed")
            found = self.game
        if found is not None:
            self.game, self.gone_since = found, None
        elif self.game is not None:
            if self.gone_since is None:
                self.gone_since = now
            elif now - self.gone_since > GRACE:
                self.game, self.gone_since = None, None

    def tick(self) -> None:
        with self.lock:
            now = time.monotonic()
            s = self.settings
            self._watch_games(now)
            wanted = s['keep'] and (not s['only_in_game'] or self.game is not None)
            if self.proc is not None and self.proc.poll() is not None:
                self._exited()
            if self.proc is not None:
                if tuple(s[k] for k in RESTART_KEYS) != self.running_key or not wanted:
                    self._stop_pipeline()
                    self.state = 'waiting' if s['keep'] else 'off'
                elif self.state == 'starting' and buffer.list_pieces(self.folder):
                    self.state = 'recording'
                    self.failures = 0
                elif self.state == 'starting' and now - self.started_at > 20:
                    self._stop_pipeline()
                    self._fail('pipeline', self._gst_tail() or 'no picture')
            elif self.state != 'starting':
                if not s['keep']:
                    self.state = 'off'
                    self._clear_problem()
                elif self.state in ('off', 'waiting'):
                    self.state = 'waiting'
                    if wanted and now >= self.retry_at:
                        self._clear_problem()
                        self._begin(interactive=False)
            if self.state == 'recording' and not self.saving:
                buffer.prune(self.folder, s['seconds'], time.time())

    def _loop(self) -> None:
        while not self.stop_event.wait(TICK):
            try:
                self.tick()
            except Exception:                      # noqa: BLE001 - keep watching
                log.exception("tick failed")

    # ─── Commands ───

    def handle(self, command: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if command == 'status':
            return self.status()
        if command == 'save':
            return self.save()
        if command == 'setup':
            return self.setup()
        if command == 'reload':
            return self.reload()
        if command in ('start', 'stop'):
            with self.lock:
                self.settings['keep'] = command == 'start'
                save_settings(self.settings)
            return self.reload(clear=True)
        if command == 'quit':
            self.stop_event.set()
            return {'ok': True}
        return {'ok': False, 'error': 'unknown command'}

    def reload(self, clear: bool = False) -> Dict[str, Any]:
        with self.lock:
            old_keep = self.settings['keep']
            fresh = load_settings()
            self.settings = fresh
            if clear or fresh['keep'] != old_keep or self.state == 'error':
                self.failures, self.retry_at = 0, 0.0
                if self.state == 'error':
                    self.state = 'waiting'
                    self._clear_problem()
            self.last_probe = 0.0
        self.tick()
        return self.status()

    def setup(self) -> Dict[str, Any]:
        """Pick the screen (the portal's dialog) now, from the window."""
        with self.lock:
            if self.proc is not None or self.state == 'starting':
                return {'ok': True, **self.status()}
            if fake():
                return {'ok': True, **self.status()}
            self._clear_problem()
            self.failures = 0
            self._begin(interactive=True)
        return {'ok': True, **self.status()}

    def status(self) -> Dict[str, Any]:
        with self.lock:
            pieces = buffer.list_pieces(self.folder) if self.proc is not None else []
            s = self.settings
            enc = self.enc if self.proc is not None else pipeline.pick_encoder(s['codec'])
            audio = pipeline.pick_audio_encoder()
            return {
                'ok': True, 'version': VERSION, 'pid': os.getpid(),
                'state': self.state, 'problem': self.problem, 'detail': self.detail,
                'game': self.game.name if self.game else None,
                'source': self.game.source if self.game else None,
                'held': buffer.seconds_held(pieces) if pieces else 0.0,
                'seconds': s['seconds'], 'keep': s['keep'], 'only_in_game': s['only_in_game'],
                'bytes': buffer.used_bytes(pieces),
                'encoder': enc.label if enc else None,
                'audio': audio[2] if audio else None,
                'tracks': self._audio_tracks(),
                'last_clip': self.last_clip,
            }

    # ─── Saving ───

    def save(self) -> Dict[str, Any]:
        with self.lock:
            if self.proc is None or self.state != 'recording':
                return {'ok': False, 'problem': 'not_recording', 'state': self.state}
            pieces = buffer.list_pieces(self.folder)
            chosen = buffer.cover(pieces[:-1], self.settings['seconds'])   # the newest is open
            if not chosen:
                return {'ok': False, 'problem': 'too_early'}
            name = clean_name(self.game.name) if self.game else ''
            name = name or games.DESKTOP
            self.saving += 1
        try:
            folder = os.path.join(clips_dir(), name)
            dst = unique_path(folder, f"{name} {stamp()}", '.mp4')
            started = time.monotonic()
            clipfile.save_clip([p.path for p in chosen], dst, folder)
            info = clipfile.probe(dst)
            seconds = int(round(info['duration'])) or len(chosen)
            log.info("saved %s (%s s) in %.1f s", dst, seconds, time.monotonic() - started)
        except (clipfile.ClipError, OSError) as exc:
            log.warning("save failed: %s", exc)
            return {'ok': False, 'problem': 'save_failed', 'detail': str(exc)}
        finally:
            with self.lock:
                self.saving -= 1
        clip = {'path': dst, 'seconds': seconds, 'game': name, 'at': time.time()}
        with self.lock:
            self.last_clip = clip
        self._tell_saved(clip)
        return {'ok': True, **clip}

    def _tell_saved(self, clip: Dict[str, Any]) -> None:
        if self.notifier is None:
            return
        try:
            number = self.notifier.show(t('notify.saved', seconds=clip['seconds']),
                                        os.path.basename(clip['path']),
                                        [('open', t('notify.open')),
                                         ('folder', t('notify.folder'))])
            if number:
                self.notes[number] = clip['path']
        except Exception:                          # noqa: BLE001 - a missing bus is no reason to fail
            log.exception("notification failed")

    def _note_action(self, number: int, action: str) -> None:
        path = self.notes.get(number)
        if not path:
            return
        self.opener(path if action == 'open' else os.path.dirname(path))

    @staticmethod
    def _xdg_open(path: str) -> None:
        tool = shutil.which('xdg-open')
        if tool:
            subprocess.Popen([tool, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)

    # ─── Running ───

    def lock_instance(self) -> bool:
        """One service per user: an advisory lock the system drops when we die."""
        path = os.path.join(runtime_dir(), 'service.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self.lock_fd = fd
        return True

    def start_background(self) -> None:
        self.server.start()
        self.tick_thread = threading.Thread(target=self._loop, daemon=True, name='clips-tick')
        self.tick_thread.start()
        self.tick()

    def shutdown(self) -> None:
        self.stop_event.set()
        self.server.stop()
        if self.tick_thread is not None:
            self.tick_thread.join(3)
        with self.lock:
            self._stop_pipeline()

    def run(self) -> int:
        """Block until told to quit (SIGTERM, SIGINT, or the quit command)."""
        if not self.lock_instance():
            log.info("another service is running; leaving")
            return 0
        self.start_background()
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, lambda *_: self.stop_event.set())
        loop = None
        try:
            from gi.repository import GLib
            loop = GLib.MainLoop()
            threading.Thread(target=lambda: (self.stop_event.wait(), loop.quit()),
                             daemon=True).start()
            loop.run()                             # the notification buttons come in here
        except ImportError:
            self.stop_event.wait()
        finally:
            self.shutdown()
        return 0
