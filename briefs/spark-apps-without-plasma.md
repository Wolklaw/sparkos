# Spark apps without Plasma (stage 3 of Replacing KDE, app side)

Goal: Spark Snip, spark-share, Spark Files, Spark Emoji and Spark Update work in a session that runs
KWin and no plasmashell. The Plasma session behaves as before. Picking is by capability (what is on
the D-Bus, what is installed), never by the desktop name.

## What each app needed

| App | KDE piece | In a Plasma-free session | Fix |
|---|---|---|---|
| Spark Snip 1.3.1 | KWin ScreenShot2; the portal | KWin ScreenShot2 works (1024x768 headless). The old order only trusted KWin when the desktop was called KDE, so an unnamed session fell to grim | `capture_order()` asks the bus (`NameHasOwner`/`ListActivatableNames`) for ScreenShot2: `kwin, portal` when offered, else `grim, portal`. `SPARK_SNIP_KWIN=1/0` forces it. Plasma and GNOME orders unchanged |
| spark-share 0.1.1 | krdpserver `--plasma` (KWin fake input and screencast) | krdpserver listens on 127.0.0.1 with KWin alone. The Tk prompt and banner need DISPLAY, which a session that never exports it lacks | `session_env` finds the Xwayland socket in `/tmp/.X11-unix` when DISPLAY is missing |
| Spark Files 1.1.1 | KIO, kio-fuse, kaccounts | kio-fuse activates and mounts a folder with no Plasma; kded6 starts once the session exports WAYLAND_DISPLAY to the bus. sftp through sshfs added for when kio-fuse is absent | New `SshFs` backend behind the same mount-point shape, chosen by `choose_backend` (kio-fuse reachable wins). `fuse-sshfs` added to the image. smb has no fallback (mount.cifs needs root); Google Drive still needs kio-gdrive and kaccounts |
| Spark Emoji (not changed) | RemoteDesktop portal | `portal_available()` is true: the KDE portal backend talks to KWin, not plasmashell | None. The session must give portal-kde a desktop name containing KDE (see below) |
| Spark Update 1.2.2 | `org.kde.Shutdown.logoutAndReboot` (ksmserver) | The call fails with no ksmserver, so Restart did nothing | Restart uses ksmserver only if `org.kde.Shutdown` has an owner, else `systemctl reboot` (logind); same fallback if ksmserver refuses |
| Spark Launcher | Plasma widget | Not touched, the shell agent moves it | |
| Spark Media, Monitor, others | `kioclient` (trash fallback), process names | gio trash runs first; the rest only names processes | Audited, no change |

The audit grep covered org.kde.plasmashell, KSplash, KRunner, ksmserver, kioclient, kde-open,
plasma-apply-* and plasmashell. Nothing else in `files/` depends on plasmashell outside the Launcher
QML, the Plasma layout files and the Klipper update script (all Plasma-session only).

## Contract for the Spark session (shell work)
- Export `WAYLAND_DISPLAY` and `XDG_SESSION_TYPE` (and `DISPLAY`/`XAUTHORITY` for Tk) into the
  systemd user and D-Bus activation environments, as a login session does; otherwise kded6 aborts on
  activation.
- xdg-desktop-portal-kde only offers Screenshot, ScreenCast and RemoteDesktop when its
  `XDG_CURRENT_DESKTOP` contains KDE. Either name the session `KDE:Spark` or start portal-kde with that value.
- Logout is the session's own quit; Restart and Shutdown go through logind (`systemctl reboot`).

## CI
`.github/workflows/spark-kwin-only.yml` runs `files/spark-apps/ci/kwin-only.sh` (headless
`kwin_wayland --virtual`, private bus, no plasmashell, portals) with `kwin_only_smoke.py` inside the
published SparkOS image. Unknown until it runs: whether KWin's virtual backend starts on a GPU-less runner.

## Tried, not tried
- Real, headless KWin on this PC: ScreenShot2 size, kio-fuse file:// mount, kded6, krdpserver listening, portal_available, self-tests (13 smoke checks pass).
- Fakes only: the portal screenshot path, Emoji paste, the sshfs backend (no sshd), Update's restart, the DISPLAY fallback.
- Not tried: Google Drive, sftp/smb through KIO in the KWin-only session, an RDP client against krdp there, the pixels of a headless capture (all black), the CI job on a runner.
