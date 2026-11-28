# Spark session: polkit agent, sign-in screen, lock screen

The security pieces of the Spark session (see [PLAN.md](../../PLAN.md)).
They are part of the image, not live-updated apps: they run as root or before anyone is signed in.
greetd with the Spark greeter is the display manager, and Spark (`spark-wl`)
is the only session.

| Piece | State |
|---|---|
| `spark-polkit`, the password prompt for system actions | Built, runs in the Spark session. |
| `spark-portal` ([portal_backend.py](sparksession/portal_backend.py)), the xdg-desktop-portal backend `org.freedesktop.impl.portal.desktop.sparkos`: settings (dark, accent, fonts), inhibit (suspend, idle, logout), notifications, access, account, email, launcher install, lockdown and print. Replaces the GTK portal. | Built, tested on a private bus; not tried on the real PC. |
| `spark-secrets` ([secrets_service.py](sparksession/secrets_service.py)), the Secret Service (`org.freedesktop.secrets`) and the Secret portal backend, with the saved passwords encrypted in `~/.local/share/spark-secrets/`. Replaces GNOME Keyring. | Built, tested on a private bus (secret-tool, secretstorage, python-keyring, a keyring from the real gnome-keyring-daemon); the sign-in unlock through greetd's PAM is not tried on a real stack. |
| `spark-greeter`, the sign-in screen on greetd | Built, the display manager. If it keeps failing, greetd switches to a text sign-in. |
| Lock screen | Spark Shell's ([lockscreen.py](../spark-shell/sparkshell/lockscreen.py)), on the compositor's ext-session-lock-v1. |

Install (the image build does this; see [files/scripts/spark-session.sh](../scripts/spark-session.sh),
and [sparkos-no-kde.sh](../scripts/sparkos-no-kde.sh), which turns greetd on):
`bash install.sh [--root DIR] [--deps] [--no-test]`.

## Spark Secrets

`spark-secrets` is a user service (D-Bus activated, `spark-secrets.service`) that owns
`org.freedesktop.secrets` and, in the same process, `org.freedesktop.impl.portal.desktop.sparksecrets`
(the Secret portal: each app gets its own random secret, made once and kept as an item).

- Storage: one file per collection in `~/.local/share/spark-secrets/` (0600, folder 0700), AES-GCM,
  written atomically. The master key is wrapped by scrypt of the login password. Item attributes
  are kept as hashes outside the encrypted part so a locked collection can still be searched.
  `login` (alias `default`) is saved; `session` lives in memory only.
- Unlock at sign-in: greetd's PAM file runs `/usr/libexec/spark-secrets-pam` (`pam_exec.so
  expose_authtok`), which writes the wrapping key to `/run/spark-secrets/UID` (0400, owned by the
  user). The daemon uses it, and it is never a reason to refuse a sign-in. With no key or a key that
  does not fit (the password changed, or the first run), the daemon asks once through `spark-ask`
  and re-wraps.
- Sessions: `plain` and `dh-ietf1024-sha256-aes128-cbc-pkcs7`.
- Import: `spark-secrets --import-gnome-keyring [~/.local/share/keyrings/login.keyring]` (the daemon
  stopped; the keyring password on a terminal prompt, or `--password-stdin`). Running it again adds
  nothing.
- SSH keys: not here. The image enables openssh's `ssh-agent.socket` for everyone and the session
  sets `SSH_AUTH_SOCK=$XDG_RUNTIME_DIR/ssh-agent.socket`.
- Chromium and Electron apps: they don't know the `sparkwl` desktop and would fall back to a key
  built into Chromium. The session sets `GNOME_DESKTOP_SESSION_ID=this-is-deprecated` (GNOME's old
  marker, the value GNOME itself uses) so they keep their keys here instead.
- Tests: `python3 -s -m unittest tests.test_secrets_store tests.test_secrets_import tests.test_secrets_service`
  (the last two start a private `dbus-daemon`; the import test needs `gnome-keyring` and `secret-tool`).

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
| `test_portal_logic.py`, `test_portal_bus.py` | a private session bus (`dbus-run-session`), no display |
| `test_greetd_real.py` | real greetd, `SPARK_ALLOW_REAL_GREETD=1` |
| `test_greeter_ctl.py` | a fake root and a fake systemctl |
| `tests/lock/run_lock_test.sh` | headless Spark compositor, `--cap-add SYS_NICE`, `SPARK_ALLOW_LOCK_TEST=1` |

CI: [.github/workflows/spark-session.yml](../../.github/workflows/spark-session.yml).
