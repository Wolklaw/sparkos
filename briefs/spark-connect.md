# Spark Connect (first part: the home servers)

Read [README.md](README.md) first for the conventions every Spark app follows. The bigger picture is
the "Remote care" section of [PLAN.md](../PLAN.md). "Spark Connect" is a working name.

## Why

The owner runs their websites on Linux machines at home: a main server that serves everything and a
standby laptop that takes over if the main server dies. When something breaks today, they find out
from a Discord alert and then SSH in by hand to work out what happened. Spark Connect puts every
machine on one screen: what's up, what's down, why, and the few fixes that are safe to do with a
click.

Later parts of the same app will add the venue laptop that runs GestionDirecte at the convention
center (through a small agent that dials out to a hub) and the GestionDirecte tablets (live screen and
remote control). **This brief is only the first part**, but build it so those slot in without a
rewrite (see "Ready for later").

## The machines

The owner's machines, their addresses, the services on each and the rules for touching them are
written down in `E:\Personal Projects\wolklaw.dev\CLAUDE.md` (on the owner's PC, not in this repo).
Read it before you start, and read its "never restart without asking" rules twice. In short:

- **The main server** runs Caddy, the Cloudflare tunnel (`cloudflared`, a user service), the
  GestionDirecte portal (system unit `gestiondirecte-portal`) and the owner's other services (sync
  server, Discord bot, more) through the same tunnel.
- **The standby laptop** runs the failover watchdog and a network monitor (user services
  `failover-watchdog` and `failover-netmon`, files in `~/failover/`). When it has taken over, it is
  the live site until someone runs its failback script.
- This PC's SSH key is already trusted by both.

**This repo is public.** Don't commit the owner's addresses, user names, hostnames of private
services or anything from `~/failover/`. The app ships with an empty machine list; the owner's list
lives only in `~/.config/spark-connect/machines.toml` on their PC.

## What it does

### Overview (the first screen)

One card per machine: name, up/down, uptime, load, memory, disk, temperature, and a one-line verdict
("All good", "cloudflared restarting", "Disk 94 % full", "Unreachable since 14:02"). Below the
machines, one row per public website with its HTTP status and response time, checked from this PC.
A machine or site that isn't fine sorts to the top and gets the magenta/cyan slip.

### Machine view

- **Services:** the systemd units the owner cares about (system and user units, listed per machine in
  the config), each with state, how long in that state, restart count and the last few log lines.
  Plus any unit that is in the `failed` state, minus the ones the owner marked as known-failed.
- **Health:** CPU, memory, disk per mount, temperature, network, last reboot.
- **Tunnel:** whether `cloudflared` is connected and how many connections it holds.
- **Failover (standby laptop):** whether the laptop is standing by or has taken over, the last
  incidents from `~/failover/incidents/` (names and first lines), and the network monitor's last
  findings. Read only.
- **Logs:** a live tail of one unit's journal, with a filter box.

### Actions

Each action says exactly what it will do and what it touches before it runs, and asks for a
confirmation. Nothing runs on a timer or on its own.

- **Open a terminal** on the machine (Konsole on SparkOS, Windows Terminal or `cmd` on Windows, running
  `ssh <host>`). This is the answer to anything the app can't do.
- **Restart a unit.** Only units listed as restartable in the config. For a user unit, plain
  `systemctl --user restart`. For a system unit, `sudo -n systemctl restart`: if sudo asks for a
  password, say so and offer the terminal instead. **Never ask for, type or store a password.**
  Restarting `cloudflared` names every hostname behind the tunnel in the confirmation, because they
  all drop for a few seconds.
- **Failback** (when the laptop has taken over): show the exact command and a button to open a
  terminal with it typed but not run. The owner presses Enter. No one-click failback in this version.
- **Copy a report:** a plain-text snapshot of one machine (services, health, last errors) to paste
  into a Claude session or a note.

No stop, disable, reboot, file editing or package installs in this version.

### Alerts

While Spark Connect is open, a machine going unreachable, a watched unit failing or a site returning
an error shows a desktop notification once, and once more when it recovers. Discord alerts stay with
the existing watchdog; don't duplicate them.

## How it talks to the machines

- **The system `ssh` client**, so the owner's existing key, `~/.ssh/config` aliases and known hosts
  just work, on SparkOS and on Windows (OpenSSH ships with Windows 10 and 11). Always
  `-o BatchMode=yes` and strict host key checking: if a host key is unknown or changed, stop and show
  it; never accept it for the owner.
- **Nothing is installed on the servers.** One refresh is one SSH call that pipes a small, read-only
  probe script to `sh -s` and gets everything back as one JSON document. The probe uses only what a
  stock Ubuntu server has (`systemctl`, `journalctl`, `/proc`, `/sys`, `df`, `ss`). It lives in the
  app as a plain file so it can be read and reviewed.
- **Refresh every 15 seconds** for the open view and every 60 seconds for the rest, and stop when the
  window is hidden. On SparkOS, reuse one connection per host (`ControlMaster`/`ControlPersist`);
  Windows' OpenSSH doesn't support that, so keep the call count low there.
- **The probe must never read secrets.** The owner's notes name a health key file and tunnel
  credentials: the probe doesn't open them, and no file contents beyond the log and incident lines
  listed above leave the server. A health URL that needs the secret header is checked on the server
  over `127.0.0.1` instead, the way the owner's Discord bot does.
- Website checks go straight from this PC with a 5 second timeout and a plain user agent
  (`SparkConnect/<version>`), no personal data.

## Ready for later

- A machine has a `kind` (`linux` now; `tablet` later) and a `transport` (`ssh` now; `hub` later, for
  machines that dial out to the hub on the main server). Keep the probe's JSON as the one format both
  transports return, so the screens don't care how the data came in.
- Keep the UI modules separate from the transport, so the tablet view (live screen and controls) can
  be added as another machine view.
- Don't build the hub, the agent or anything for tablets now.

## Runs on SparkOS and Windows

Python 3 and Tk like the other Spark apps, with no third-party packages unless one is truly needed
(then pure Python, bundled in the app folder). On SparkOS: the usual `install.sh --user` /
`--uninstall` / `--self-test`. On Windows: runs from source with the Python launcher (`py
spark_connect.py`); a Windows installer is a later step, not this brief. `--self-test` checks that
`ssh` is on the path, that the config parses, and that the probe script is present. It does not
connect to anything.

## Look

The house style, desktop tool variant (see README). Machines as cards on a dark field, states as
uppercase micro-labels, numbers in mono. The slip is for trouble only: a calm screen has none.

## Tests

- **Unit:** the probe's JSON parser against fixture outputs in `tests/fixtures/` (all fine, a failed
  unit, a full disk, `cloudflared` reconnecting, the standby laptop after a takeover, a machine that
  times out, a changed host key); the verdict line for each; the config loader; the confirmation text
  for each action (the `cloudflared` one lists hostnames).
- **The probe itself:** run it in CI inside a `fedora:latest` container and an `ubuntu:24.04`
  container and check that it prints valid JSON with the expected keys, and that it exits cleanly
  when `systemctl` has no systemd to talk to.
- **SSH end to end:** in CI, start `sshd` in a container with a throwaway key and a dummy user unit,
  connect through the real `ssh` client, refresh, and restart the dummy unit.
- **UI under Xvfb:** overview with fixture data renders; a failed machine sorts to the top; the
  restart confirmation shows and cancelling it runs nothing.
- CI inside the SparkOS image: `install.sh --user`, `--self-test`, `--uninstall` as a normal user,
  plus the unit tests on `windows-latest`.
- **Against the owner's real machines: read only, and only with the owner watching.** Ask before the
  first connection. Never restart a real unit to test the button.

## Done when

CI passes on Fedora, inside the SparkOS image and on Windows; the app installs and uninstalls for one
user with no root; the owner has seen their two machines on the overview from their own PC; and the PR
is open for the owner. It is an optional app, so it is not added to the Containerfile or the boot test.
