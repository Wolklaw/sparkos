# Spark session: polkit agent, sign-in screen, lock screen

The security pieces of the Spark session (stage 3 of "Replacing KDE" in [PLAN.md](../../PLAN.md)).
They are part of the image, not live-updated apps: they run as root or before anyone is signed in.
Spark (`spark-wl`) is the default session; Plasma is the fallback. Plasma Login Manager stays the display manager.

| Piece | State |
|---|---|
| `spark-polkit`, the password prompt for system actions | Built. Used only in the Spark session. |
| `spark-greeter`, the sign-in screen on greetd | Built, installed, **not enabled**. `spark greeter enable` opts in. |
| Lock screen | Not built. KWin has no way to host one yet, so the Spark session keeps kscreenlocker. |

Install (the image build does this; see [files/scripts/spark-session.sh](../scripts/spark-session.sh)):
`bash install.sh [--root DIR] [--deps] [--no-test]`.

## Lock screen: what KWin offers

KWin 6.8.3 (Fedora 45) does not advertise `ext_session_lock_manager_v1`; it does advertise
`ext_idle_notifier_v1`. A lock screen made of a layer-shell window would not be a lock: a client
crash or a keyboard shortcut would leave the desktop open. So no `spark-lock` was built and
kscreenlocker stays. [tests/lock/run_lock_test.sh](tests/lock/run_lock_test.sh) records whether
this KWin has the protocol (CI prints a notice the day it does) and proves that killing the
kscreenlocker greeter leaves the session locked.

What a Spark lock needs once KWin has ext-session-lock-v1:

- A GTK4 client that binds `ext_session_lock_manager_v1`, makes one lock surface per output, and
  shows a password field in the house style.
- PAM (`pam_unix` through a `spark-lock` service file) for the check, run off the UI thread.
- logind: lock on `Lock`, unlock on `Unlock`, set the locked hint, lock before sleep.
- Idle locking through `ext_idle_notifier_v1`.
- Fail closed: if the client dies the compositor keeps the screen locked, and a supervisor
  restarts the client.

## Polkit agent

`/usr/bin/spark-polkit` registers as the session's authentication agent at
`/dev/wolklaw/SparkPolkit/AuthenticationAgent` and shows a dialog when something needs a password.
It never writes the password to a log, a file or the process list; it hands it to polkit's own
helper (`polkit-agent-helper-1`) and clears it.

Command line for the Spark session script (start it once per session, after the compositor):

```
/usr/bin/spark-polkit &
```

- Set `XDG_CURRENT_DESKTOP` to something other than `KDE` in the Spark session, or polkit-kde's
  autostart starts a second agent.
- It exits with status 1 and a message on stderr if another agent already holds the session.
- `spark-polkit --version`, `--self-test`.
- Language follows `SPARK_LANG`, then the locale (English and French).

## Sign-in screen (greetd)

`spark-greeter` is a GTK4 window run by KWin as a bare compositor
(`/usr/libexec/spark-greeter-session`), as the `greetd` user. It lists users and sessions, asks
for the password (and any extra question PAM asks), remembers the last user and session, and has
sleep, restart and shut down buttons. A polkit rule
([50-spark-greeter.rules](system/usr/share/polkit-1/rules.d/50-spark-greeter.rules)) lets the
`greetd` account do exactly those three power actions.

```
spark greeter status    what signs you in now, and whether the Spark screen is ready
spark greeter enable    from the next restart: greetd + Spark greeter
spark greeter disable   from the next restart: Plasma Login Manager again
```

`enable` copies [greetd-config.toml](system/usr/share/spark-session/greetd-config.toml) to
`/etc/greetd/config.toml` (the original goes to `config.toml.pre-spark`), records the current
display manager in `/var/lib/spark-greeter/previous-dm`, disables it and enables `greetd.service`.
It never starts or stops anything, so the running session is untouched.

### If the screen does not come up

1. Automatic: `greetd.service` has `OnFailure=spark-greeter-fallback.service`, which runs
   `spark-greeter-ctl auto-rollback` (disable greetd, start Plasma Login Manager). Four failed
   starts in a minute trigger it.
2. Ctrl+Alt+F3, sign in on the text console, run `spark greeter disable`, restart.
3. From a live USB or another machine: delete `/etc/systemd/system/display-manager.service` and
   run `systemctl enable plasmalogin.service`, or boot the previous image from the boot menu
   (`rpm-ostree` keeps it).

## Tests

All in containers or CI. Nothing opens a window on a desktop, locks a screen or starts a display
manager.

| Test | Needs |
|---|---|
| `test_polkit_fake_authority.py`, `test_polkit_flow.py` | dbusmock |
| `test_polkit_real.py` | real polkitd (the `pkcheck` round trip skips without logind) |
| `test_polkit_window.py`, `test_greeter.py` | Xvfb |
| `test_greetd_real.py` | real greetd, `SPARK_ALLOW_REAL_GREETD=1` |
| `test_greeter_ctl.py` | a fake root and a fake systemctl |
| `tests/lock/run_lock_test.sh` | headless KWin, `--cap-add SYS_NICE`, `SPARK_ALLOW_LOCK_TEST=1` |

CI: [.github/workflows/spark-session.yml](../../.github/workflows/spark-session.yml).
