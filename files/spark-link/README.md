# Spark Link

Your phone and this PC, linked over the local network with no account and no outside server. It replaces KDE Connect with something both ends of which are SparkOS's own: this is the PC side; the phone side is the "Link to PC" section of Soot's Android app. The two follow [docs/spark-link-protocol.md](../../docs/spark-link-protocol.md).

Version 1 does:

- **Links:** a tab or link sent from the phone opens in Soot on the PC (the default browser if Soot isn't there), and "Send a link" sends one back. Only `http://` and `https://`.
- **Files:** files from the phone land in Downloads; you accept each one unless you switched on "Accept files without asking" for that phone. "Send files", or right-click > **Send to phone** in Dolphin, sends files the other way. Every file is checked against its SHA-256 before it's kept, and nothing is overwritten.
- **Phone notifications** show as Plasma notifications (read-only; no replies in v1).
- **Battery:** the phone's level in the window, and a warning at 15 % while it isn't charging.
- **Find my phone:** "Ring" makes the phone ring at full volume until you tap it.
- **Shared clipboard:** text copied on one side can be pasted on the other. **Off until you switch it on**, because everything you copy would go to the phone.

Each one can be switched off on the Features tab. Not in v1: SMS, calls, media control, remote input, screen mirroring.

## How it works

- **Two parts.** A background service (`spark-link --service`, a systemd user unit) does the talking; the window (`spark-link`) pairs phones and switches features. They talk over a Unix socket in `$XDG_RUNTIME_DIR/spark-link/` that only you can open (the service checks the caller's user ID too).
- **Off until used.** The unit isn't switched on for anyone who never paired a phone; the window enables it (`systemctl --user enable --now spark-link.service`) the first time you pair. Even running, the service listens on the network, and announces itself over mDNS, only while a phone is paired or the pairing screen is open.
- **Pairing.** The PC has its own ECDSA P-256 key and self-signed certificate, made with `openssl` on first run in `~/.local/share/spark-link/` (0600). "Show a pairing code" makes a 6-digit one-time code and shows a QR code of a `sparklink://pair?...` link holding this PC's address, ID, certificate fingerprint and the code; the same link as text to copy; and the address, code and a 16-character key check for typing by hand. The phone connects over TLS 1.3, checks the PC's certificate against the fingerprint, and sends the code and its own certificate. You confirm on the PC ("Pair with Pixel 8?"). The code works once, lives 5 minutes, and five wrong codes end the pairing session. Closing the window ends pairing too.
- **After pairing** every connection is mutual TLS 1.3: the PC trusts exactly the certificates of the phones paired with it, and the phone trusts exactly this PC's. A phone the PC doesn't know fails the TLS handshake. Connections are accepted only from private, link-local and loopback addresses.
- **Light.** The service waits in an event loop: with no phone connected nothing runs at all; with one connected, the phone's ping every 30 seconds is the only regular wake-up. CI measures its CPU use while idle.
- **Desktop.** Notifications and the clipboard go through D-Bus (GObject's Gio): `org.freedesktop.Notifications`, and Plasma's Klipper (`org.kde.klipper`) for the clipboard, falling back to `wl-copy`/`wl-paste`. The mDNS announcement goes through Avahi's D-Bus API. Phone notification text is shown as plain text (Plasma's markup is escaped).
- **Firewall.** The image build step ([spark-link.sh](../scripts/spark-link.sh)) installs a firewalld service definition (`spark-link`, TCP 47100) and opens it in the default zone unless that zone already allows the port (Fedora's desktop zone allows 1025-65535).
- Nothing is logged of what passes through: no clipboard text, notification contents, file contents or pairing codes. The log is `~/.local/state/spark-link/spark-link.log`, settings `~/.config/spark-link/`.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (the image build)
spark-link                                # the window
spark-link --tab pair                     # open on Pair a phone
spark-link --send FILE...                 # send files to the connected phone
spark-link --send-url https://...         # send a link
spark-link --ring                         # ring the phone
spark-link --status                       # what the service is doing
spark-link --self-test                    # what it needs and finds here; no display or phone
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs what the SparkOS image already has (Python 3 with tkinter and ssl, the `openssl` command; GObject for notifications, the clipboard and mDNS). It installs to `~/.local/lib/spark-link/`, `~/.local/bin/spark-link`, `~/.local/share/applications/`, `~/.local/share/icons/`, `~/.local/share/kio/servicemenus/` (Dolphin's Send to phone) and `~/.config/systemd/user/spark-link.service`, and lists every file in `~/.local/lib/spark-link/installed-files` for `--uninstall`, which also stops and disables the service. Your key, paired phones and settings are left in place.

`spark-app.json` describes the app for the Spark Portal.

**Tests.** `tests/linkclient.py` is a reference phone written from the protocol document alone (it shares no protocol code with the service), and `tests/test_protocol.py` runs it against the real service, started as its own process and driven over the real control socket like the window does: pairing (both kinds of phone certificate), reconnecting, a new connection replacing the old, every feature both ways, and the failure cases: wrong code, five wrong codes, a declined or unanswered pairing, a reused code, a PC with the wrong fingerprint, an unpaired phone's certificate, a connection without a certificate trying more than `pair`, a hello with another phone's ID, unpairing from either side, oversize and broken frames, damaged, cancelled and out-of-order files, and the idle, confirm and offer timeouts. `test_units.py` covers the parts (file names from phones, addresses, the paired-phone store, keys, the QR encoder, strings); `test_ui.py` the window, with a stand-in service. CI ([workflow](../../.github/workflows/spark-link.yml)) runs the image build step and all tests in Fedora (the window under Xvfb, QR codes read back by zbar), checks the mDNS announcement through a real Avahi and the idle CPU, and inside the published SparkOS image installs it with `--user` as a normal user, runs the self-test and the same tests on the image's Python and OpenSSL, and uninstalls it.

## Not verified yet (needs a real phone or a real desktop)

- **With a real phone.** The phone side (Soot's app) was built at the same time by another session against the same document and tested on an Android emulator against a Python stand-in using this service's TLS settings; it hasn't met this service itself yet. First things to try: pairing by QR, then each feature, then walking out of Wi-Fi range and back (reconnect).
- **On a SparkOS desktop.** Not run on Plasma 6.8 yet: the Plasma notifications, Klipper's D-Bus clipboard on Plasma 6.8, Dolphin's Send to phone menu, the KDE file picker, starting at login through `graphical-session.target`, and the window's look at the desktop's scaling. CI has no session bus, so those paths are only exercised by the self-test's reporting.
- **mDNS on a real network.** Tested with Avahi inside a container, not across Wi-Fi to an Android phone; some routers block multicast, which is what the pairing link and typed address are for.
- **Soot's "send this tab to phone".** Soot can call `spark-link --send-url <url>`; Soot needs a menu item or toolbar button that runs it with the current tab's address (a native-messaging host, or a small extension calling one). Nothing in Soot does that yet.
- English only; every sentence is in `sparklink/text.py`, ready for a French table.
- A second window can open if you start Spark Link while one is open.
