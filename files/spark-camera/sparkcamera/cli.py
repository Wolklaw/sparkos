"""The command line. --version and --self-test never load a window and never touch your files:
the self-test records a second of test pattern and test tone into a temporary folder it makes
and removes, so it needs no camera and no microphone."""

import argparse
import os
import shutil
import sys
import tempfile
import time
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def _wait_frame(session) -> bool:
    end = time.monotonic() + 5
    while time.monotonic() < end:
        if session.new_preview() is not None:
            return True
        time.sleep(0.05)
    return False


def _wait_events(poll, seconds: float = 8.0) -> list:
    events: list = []
    end = time.monotonic() + seconds
    while not events and time.monotonic() < end:
        time.sleep(0.05)
        events += poll()
    return events


def _pipelines(media, video, voice, tmp: str, failures: List[str]) -> None:
    """The same pipelines the window uses, on a test pattern and a test tone."""
    from .core import human_size
    cam, mic = media.list_cameras()[0], media.list_mics()[0]
    mode = media.pick_mode(cam.modes, '640x480') or cam.modes[0]
    session = media.CameraSession(cam, mode)
    try:
        session.start()
        got = _wait_frame(session)
        print(f"preview:   {'first picture arrived' if got else 'NO PICTURE'}")
        if not got:
            failures.append("preview")
        time.sleep(0.5)
        frame = session.photo_frame()
        if frame is not None:
            from PIL import Image
            path = os.path.join(tmp, 'photo.jpg')
            media.rgb_to_image(*frame).save(path, 'JPEG')
            with Image.open(path) as image:
                ok = image.size == (frame[0], frame[1])
            print(f"photo:     {frame[0]}x{frame[1]} JPEG, {human_size(os.path.getsize(path))}"
                  f"{'' if ok else '  (WRONG SIZE)'}")
            if not ok:
                failures.append("photo")
        else:
            print("photo:     NO FRAME")
            failures.append("photo")
        for fmt in video:
            path = os.path.join(tmp, 'clip-' + fmt.key + fmt.ext)
            session.start_recording(path, fmt, mic)
            time.sleep(1.2)
            session.stop_recording()
            events = _wait_events(session.poll)
            length = media.file_duration(path)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            ok = bool(events) and size > 0 and 0.5 <= length <= 3.0
            print(f"video:     {fmt.label} with sound, {length:.1f} s, {human_size(size)}"
                  f"{'' if ok else '  (WRONG)'}")
            if not ok:
                failures.append("video " + fmt.key)
    finally:
        session.stop()
    for fmt in voice:
        path = os.path.join(tmp, 'voice' + fmt.ext)
        recorder = media.VoiceSession(mic, fmt, path)
        recorder.start()
        time.sleep(1.0)
        recorder.finish()
        events = _wait_events(recorder.poll)
        length = media.file_duration(path)
        ok = bool(events) and 0.5 <= length <= 2.5
        print(f"voice:     {fmt.label}, {length:.1f} s{'' if ok else '  (WRONG)'}")
        if not ok:
            failures.append("voice " + fmt.key)


def self_test() -> int:
    from . import media, text
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    try:
        import PIL
        from PIL import ImageTk  # noqa: F401
        print(f"pillow:    {PIL.__version__} with ImageTk")
    except ImportError as exc:
        print(f"pillow:    MISSING ({exc})")
        failures.append("pillow")
    missing = [k for k in text.EN if k not in text.FR]
    print(f"text:      {len(text.EN)} strings, French "
          f"{'complete' if not missing else 'missing ' + ', '.join(missing)}")
    if missing:
        failures.append("text")

    err = media.init()
    if err:
        print(f"gstreamer: MISSING ({err})")
        print("FAILED: gstreamer")
        return 1
    print(f"gstreamer: {media.Gst.version_string()}")
    video = media.video_formats()
    voice = media.voice_formats()
    print("video:     " + (", ".join(f.label for f in video) or "NO ENCODER"))
    print("voice:     " + (", ".join(f.label for f in voice) or "NO ENCODER"))
    if not video:
        failures.append("video encoders")
    if not voice:
        failures.append("voice encoders")

    # the real devices, for information only: a PC without a camera is not a failure
    real_cameras = media.list_cameras()
    real_mics = media.list_mics()
    print(f"cameras:   {len(real_cameras)} found"
          + "".join(f"\n             {c.name} ({len(c.modes)} sizes)" for c in real_cameras))
    print(f"mics:      {len(real_mics)} found"
          + "".join(f"\n             {m.name}" for m in real_mics))

    previous = os.environ.get('SPARK_CAMERA_FAKE')
    os.environ['SPARK_CAMERA_FAKE'] = '1'
    tmp = tempfile.mkdtemp(prefix='spark-camera-selftest-')
    try:
        _pipelines(media, video, voice, tmp, failures)
    except Exception as exc:                       # noqa: BLE001 - say what broke
        print(f"pipelines: FAILED ({exc})")
        failures.append("pipelines")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if previous is None:
            os.environ.pop('SPARK_CAMERA_FAKE', None)
        else:
            os.environ['SPARK_CAMERA_FAKE'] = previous
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: a webcam with "
                                     "photos and video, and a voice recorder.")
    parser.add_argument('--tab', choices=('camera', 'voice'), default='camera',
                        help="open on this tab (default camera)")
    parser.add_argument('--self-test', action='store_true',
                        help="check the install with a test pattern and a test tone, in a "
                             "temporary folder; needs no display, camera or microphone")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App
    try:
        app = App(tab=args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
