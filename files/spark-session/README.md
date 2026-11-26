# Spark session: polkit agent, sign-in screen, lock screen

The security pieces of the Spark session (stage 3 of "Replacing KDE" in [PLAN.md](../../PLAN.md)).
They are part of the image, not live-updated apps: they run as root or before anyone is signed in.
The image has no KDE: greetd with the Spark greeter is the display manager, and Spark (`spark-wl`)
is the only session.

| Piece | State |
|---|---|
| `spark-polkit`, the password prompt for system actions | Built, runs in the Spark session. |
| `spark-greeter`, the sign-in screen on greetd | Built, the display manager. If it keeps failing, greetd switches to a text sign-in. |
| Lock screen | Spark Shell's ([lockscreen.py](../spark-shell/sparkshell/lockscreen.py)), on the compositor's ext-session-lock-v1. |

Install (the image build does this; see [files/scripts/spark-session.sh](../scripts/spark-session.sh),
and [sparkos-no-kde.sh](../scripts/sparkos-no-kde.sh), which turns greetd on):
`bash install.sh [--root DIR] [--deps] [--no-test]`.

## Sign-in screen (greetd)

`spark-greeter` is a GTK4 window, the only window of a spark-compositor started for it
(`/usr/libexec/spark-greeter-session`), as the `greetd` user. It lists users and sessions, asks
for the password (and any extra question PAM asks), remembers the last user and session, and has
sleep, restart and shut down buttons. A polkit rule
([50-spark-greeter.rules](system/usr/share/polkit-1/rules.d/50-spark-greeter.rules)) lets the
`greetd` account do exactly those three power actions.

```
spark greeter status    what signs you in now, and whether the Spark screen has what it needs
spark greeter enable    from the next restart: the Spark sign-in screen (the default)
spark greeter disable   from the next restart: greetd's text sign-in (agreety), which still starts
                        the Spark session
```

Both copy a file to `/etc/greetd/config.toml` ([greetd-config.toml](system/usr/share/spark-session/greetd-config.toml)
or [greetd-text.toml](system/usr/share/spark-session/greetd-text.toml)) and make sure greetd is the
display manager. They never start or stop anything, so the running session is untouched.

### If the screen does not come up

1. Automatic: `greetd.service` has `OnFailure=spark-greeter-fallback.service`, which runs
   `spark-greeter-ctl auto-rollback`: the text sign-in, and greetd started again. Four failed
   starts in a minute trigger it.
2. Ctrl+Alt+F3, sign in on the text console, run `spark greeter disable`, restart.
3. Boot the previous image from the boot menu (`rpm-ostree` keeps it).

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
| `tests/lock/run_lock_test.sh` | headless KWin, `--cap-add SYS_NICE`, `SPARK_ALLOW_LOCK_TEST=1`. Written for the old Plasma session; it checks KWin's lock, not the Spark compositor's |

CI: [.github/workflows/spark-session.yml](../../.github/workflows/spark-session.yml).
