# Spark Connect

Your home servers on one screen: what's up, what's down, why, and the few fixes that are safe to do with a click. It talks to each machine with your own `ssh`, so your key, `~/.ssh/config` aliases and known hosts work as they do in a terminal. Nothing is installed on the servers.

This is the first part ([brief](../../briefs/spark-connect.md)): Linux machines over SSH. Later parts add the venue laptop (through a small agent that dials out to a hub) and the GestionDirecte tablets. "Spark Connect" is a working name. It is an optional Spark app: not in the SparkOS image, installed per user.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

## What it shows

- **Overview:** one card per machine with up/down, uptime, load, memory, fullest disk, hottest sensor, and a one-line verdict ("All good", "example-portal failed", "Disk 94% full (/)", "Unreachable since 14:02"). Below them, one row per website with its HTTP status and response time, checked from this PC. Anything that isn't fine sorts to the top and gets the magenta/cyan slip; a calm screen has none.
- **Machine view:**
  - **Services:** the units listed in the config (system and user), each with state, how long in that state, restart count and the last 5 log lines; plus any other failed unit, minus the ones marked known-failed.
  - **Health:** OS and kernel, CPU, load, memory, swap, each disk, temperatures, network rate, last reboot, updates waiting, and whether an update waits on a reboot (Ubuntu's `/var/run/reboot-required`, which also puts "Reboot needed" on the machine's card).
  - **Tunnel:** whether the tunnel's unit runs and how many connections it holds, and the sites behind it.
  - **Failover** (machines with a `[machine.failover]` section): standing by or taken over, the newest incident files (name, date, first line) and the network monitor's last lines. Read only.
  - **Logs:** a live tail of one unit's journal, with a filter box. It runs only while that tab is open.

## What it can do

Every action says what it will run and what it touches, and runs only after you confirm.

- **Open terminal:** Spark Terminal (or Konsole, or another terminal) running `ssh <host>`; on Windows, a new console window.
- **Restart** a unit listed as `restartable` in the config. User units: `systemctl --user restart`. System units: `sudo -n systemctl restart`; if sudo wants a password nothing runs, and it offers a terminal with the command typed instead. It never asks for, types or stores a password. Restarting the tunnel names every hostname behind it in the confirmation.
- **Failback** (shown only when a standby has taken over): opens a terminal on the standby with the failback command typed but not run. You press Enter.
- **Update…** (machines with `allow = ["update", ...]`): opens a terminal on the machine running `sudo apt update && sudo apt full-upgrade` (or `sudo dnf upgrade --refresh`). The package manager lists the changes and asks before it does anything; sudo asks for its password there if it needs one.
- **Reboot…** (machines with `allow = [..., "reboot"]`): `sudo -n systemctl reboot`, after a confirmation that names the sites behind the machine's tunnel and, if a standby `watches` it, says the standby may take over and needs a failback afterwards. If sudo wants a password nothing runs, and it offers a terminal with the command typed instead. For ten minutes after, the machine shows as rebooting, not unreachable, and sends no notification.
- **Copy report:** a plain-text snapshot of one machine (services, health, last errors) for a note or a Claude session. Copying runs nothing, so it doesn't ask first.

- **Take control** and **Take control without asking…** (machines with `desktop = true`, SparkOS desktops only, never the servers): see and control that desktop in a FreeRDP window (`mstsc` on Windows). See below.

No stop, disable or file editing, and no update or reboot on machines whose config doesn't allow it. Nothing runs on a timer or by itself.

While it is open, a machine going unreachable, a watched unit failing or a site returning an error shows a desktop notification once, and once more when it recovers (Linux, through `notify-send`; on Windows the window's status line shows it instead). It doesn't send Discord alerts; the servers' own watchdog does that.

## Take control of a desktop

A machine with `desktop = true` shows whether someone is logged in, whether the screen is locked, and two buttons. It needs `spark-share` on that machine, which ships in the SparkOS image (`/usr/bin/spark-share`); on this PC it needs FreeRDP (`sdl-freerdp`, `xfreerdp3` or `xfreerdp`) or, on Windows, `mstsc`.

- **Take control:** runs `ssh <host> spark-share request --control`. The person at that screen gets a window naming who is asking and from which PC, with Deny as the default. No answer in 30 seconds counts as Deny. Nothing starts until they press Allow.
- **Take control without asking…:** runs `sudo -n spark-share request --control --no-ask`. No prompt. It works only with passwordless sudo on that machine, or after you type the sudo password in a terminal Spark Connect opens for it. A banner still shows on that screen the whole time, with a Stop button.
- Either way: `spark-share` starts KDE's RDP server (`krdpserver --plasma`) for one share, on `127.0.0.1` only, with a one-time user, password and certificate. Spark Connect forwards a local port to it over the same SSH login and opens the viewer on that port. Nothing listens on the network. The share ends when you press Stop, close the viewer, the SSH connection drops, krdpserver exits or after two hours, and the credentials and certificate go with it.
- The machine's card shows "Screen shared, N min" with a Stop button while one is open. A locked screen can't answer the prompt, so Take control says so up front; only the override works then.
- The prompt is consent for the person at the screen, not a security wall: anyone with SSH as that desktop's own user could start krdp themselves. The SSH key is what keeps strangers out, as everywhere else in this app.
- The viewer gets its password through its standard input (FreeRDP `/args-from:stdin`; on Windows `cmdkey`, removed when the share ends), never in a command line on this PC.

## See the console of a server with no desktop

A machine with `console = true` (for a machine with no desktop, such as a GestionDirecte host; not with `desktop = true`) gets **See console**. It opens a terminal (Spark Terminal on SparkOS, a console window on Windows) running `ssh -t <host> sudo python3 -c <script> <this PC's name>`, and nothing is installed on the server.

- **It is always the sudo path.** Reading the server's screen (`/dev/vcsa1`) needs root, so you type the server's sudo password in that terminal. There is no approval prompt and nobody at the server is asked. After the confirmation dialog, that is the whole gate; it is meant for your own servers.
- The script (`sparkconnect/console.py`, readable in this folder) copies the text and the cursor of the server's first console a few times a second into your terminal. **Q** or **Ctrl+C** closes it.
- **Ctrl+]** switches "type into the console" on and off. Typing goes through a virtual keyboard (`/dev/uinput`), made in pure Python, because pushing keystrokes into a console with `TIOCSTI` is switched off on current kernels (sysctl `dev.tty.legacy_tiocsti`). It assumes a US keyboard layout and drops keys it has no mapping for. It types only while tty1 is the console in front.
- While it runs, it writes one line on tty1 saying which PC is viewing, another when typing starts and stops, and one when it ends.
- Never run against a real GestionDirecte host so far. Tested: the screen it draws from a fixture dump, the key decoding, the notices and the loop with a fake keyboard, and the command line. Not tested: `/dev/vcsa1` and `/dev/uinput` on a real server, uinput in CI, the sudo-password terminal, and the Windows quoting of the long `-c` argument.

## The machine list

`~/.config/spark-connect/machines.toml` (Windows: `%APPDATA%\spark-connect\machines.toml`). Spark Connect only reads it and never creates it; it starts with no machines. Copy [machines.example.toml](machines.example.toml), which shows every field with made-up names, and press F5 in the window after changing it.

Unit names, the host, paths and health URLs are checked against a short list of safe characters when the file is read, and quoted again where they are used. `host` can't start with `-`. `local_checks` only accepts URLs on `127.0.0.1` or `localhost`: they are fetched on the server itself, for health endpoints that aren't public, so the app never needs a secret header or key file.

## How it talks to the machines

- One refresh is one SSH call: the probe ([sparkconnect/probe.sh](sparkconnect/probe.sh)) is piped to `sh -s` with that machine's settings set above it, and prints one JSON document. It only reads `/proc`, `/sys`, `/etc/os-release`, `df`, `ss`, `systemctl show`, `journalctl` for the listed units, the failed-unit list, and on a standby the incident file names and first lines and the monitor log's last lines. It opens no other file: no keys, no credentials, no configuration. It uses only what a stock Ubuntu or Fedora server has, and without systemd it still answers (with no units).
- Always `-o BatchMode=yes -o StrictHostKeyChecking=yes`. An unknown or changed host key stops the refresh; the machine shows the message and the fingerprint ssh printed, and you check and accept the key yourself in a terminal.
- Every 15 seconds for the machine that is open, every 60 seconds for the rest and the websites; nothing while the window is minimized. All SSH calls and site checks run on worker threads, so the window never waits.
- On Linux one connection per host is reused (`ControlMaster`, socket in `~/.cache/spark-connect/`, closed 2 minutes after the last call). Windows' OpenSSH can't do that, so each refresh there is a new connection.
- Website checks: one GET from this PC, 5 second timeout, user agent `SparkConnect/0.1.0`, nothing else.
- Ready for later: a machine has a `kind` (`linux`) and a `transport` (`ssh`); the screens only see the probe's JSON, so a hub transport can return the same format, and a tablet view can be added beside the machine view (`sparkconnect/views.py`). Neither exists yet.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages
spark-connect
spark-connect --config FILE               # another machine list
spark-connect --self-test                 # ssh on the path, the list parses, the probe is there; connects to nothing
py spark_connect.py                       # Windows, from this folder (no installer yet)
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

F5 reads the machine list again and refreshes everything, Escape goes back to the overview, Ctrl+W closes. Needs Python 3.11 or newer (for `tomllib`) with tkinter, and the OpenSSH client. The log is in `~/.local/state/spark-connect/`.

## Tests

- **Screen sharing** ([tests/test_share.py](tests/test_share.py)): `spark-share` run against a fake krdpserver, session lookup, the prompt and banner in English and French with no clipped text, the viewer command lines (no password in argv, certificate pinned), `mstsc` credentials removed, the share lifecycle through a fake ssh.

- **Unit** (fixtures in `tests/fixtures/`, made-up machines): the probe's JSON for all fine, a failed unit, a full disk, the tunnel reconnecting, the standby standing by and after a takeover; ssh's own output for a timeout, a changed host key, an unknown host key and a refused key; the verdict for each; the config loader and its errors; the confirmation text for each action (the tunnel one lists hostnames); the restart command and sudo's password refusal through a stand-in `ssh`; that the typed failback line doesn't run without Enter; alerts, the report, website checks against a local server.
- **UI under Xvfb:** the overview renders calm with no slip; a failed machine sorts to the top and slips, and sorts back when it answers; the restart confirmation shows the hostnames and cancelling it runs nothing; every tab of the machine view; the log tail and its filter; no clipped text in English or French.
- **CI** ([workflow](../../.github/workflows/spark-connect.yml)): the tests in Fedora (English and French) after a system-wide install; the probe in plain `fedora:latest` and `ubuntu:24.04` containers; SSH end to end against a throwaway container with sshd, systemd, a throwaway key and a dummy user unit (refresh, restart the unit and see it restarted, sudo's password refusal, an unknown host key refused, a journal tail); the unit tests on `windows-latest`; and inside the published SparkOS image, `install.sh --user`, `--self-test`, the tests and `--uninstall` as a normal user.

## Known gaps

- **Take control has not been tried on a real desktop.** Tested: `spark-share` against a fake krdpserver (the JSON line, 127.0.0.1 only, Deny and timeout start nothing, a locked screen is refused, Stop and a closed connection end it), the share lifecycle through a fake ssh, the viewer command lines, and the prompt and banner in English and French. Tried by hand on a Plasma PC, in a throwaway virtual KWin (not the desktop in use): `krdpserver --plasma` starts on `127.0.0.1`, and FreeRDP `/auth-only` with the pinned certificate (`/cert:fingerprint:sha256:<hex>,deny`) signs in, while a wrong fingerprint is refused. **Not in CI:** a headless KWin (`kwin_wayland --virtual`) would not start in a container without a GPU, neither in plain Fedora nor in the SparkOS image, so there is no end-to-end CI job. Not tried at all: the prompt and banner on a real session, a real mouse and keyboard through the viewer, Windows' `mstsc`, and the sudo-password terminal. The owner does the first real share while watching.
- **No view-only.** krdp 6.8 has no such option, so there is no "See screen": every share is controlled. Revisit when krdp adds one.
- **The one-time password is visible to local users on the target** (`/proc/<pid>/cmdline` of `krdpserver`) while a share runs, because krdpserver only takes its password as an argument or from KWallet. It is random, single use, bound to `127.0.0.1`, and gone when the share ends. On a desktop with one person, that is the person you are connecting to.
- **Windows' `mstsc` can't pin the certificate**; it relies on the SSH forward to `127.0.0.1` and the one-time password.
- Taking control of a session that belongs to another user than the SSH login works only through the override (root).

- **Not yet tried against the owner's real machines.** The first real connection is for the owner to do while watching; read only, no restart to test the button.
- **Windows:** runs from source; no installer, no desktop notifications, and no connection reuse (each refresh is a new SSH connection). Open terminal and Failback open a plain console window running `ssh`.
- **Tunnel connections** are counted with `ss` from the tunnel's own user, which assumes the tunnel runs as the same user Spark Connect logs in as (a user service). For a tunnel run as another user the count reads 0 and the verdict wrongly says it is reconnecting.
- **System unit logs** need the login user to be allowed to read the system journal (the `adm` or `systemd-journal` group); otherwise the log lines are empty and the row says so.
- Incident file names with spaces aren't listed.
