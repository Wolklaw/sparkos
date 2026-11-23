# Spark Connect: see and control a desktop (second part)

Read [README.md](README.md) and [spark-connect.md](spark-connect.md) first. This adds remote screen
and control to Spark Connect for machines that have a desktop. The home servers (Ubuntu, no screen,
no keyboard) don't get it: their machine view stays as it is.

## What the owner asked for (2026-11-23)

> Let me take remote control if needed, like see the desktop, through an approval if needed (with a
> sudo override), except for my Ubuntu home servers since they don't have keyboards.

So:

1. From a machine's view in Spark Connect, **See screen** and **Take control**.
2. **Approval:** the person at that machine gets a prompt and decides. Nothing is shown until they
   accept.
3. **Sudo override:** when nobody is there to accept (or nobody is logged in to answer), the owner
   can skip the prompt by proving admin rights on that machine with `sudo`.
4. Only machines marked as having a desktop.

## How it works

Nothing new listens on the network, and the stream needs no new software: SparkOS's image already
has KDE's RDP server (`krdpserver`, krdp 6.8, part of Plasma) and the FreeRDP client (`xfreerdp`,
`sdl-freerdp`; krdp is built on FreeRDP).

1. Spark Connect runs `ssh <host> spark-share request --control|--view --from "<this PC's name>"`
   on the target (same SSH rules as part one: `BatchMode`, strict host keys, the owner's own key).
2. `spark-share` (new, on the target, see below) finds the active graphical session, and shows the
   **approval prompt** in it: "<Owner> wants to see this screen" / "...see and control this screen",
   from which PC, with **Allow** and **Deny**. No answer in 30 seconds counts as Deny. A locked screen
   or no one logged in counts as no answer.
3. On Allow, `spark-share` starts `krdpserver --plasma` in that session, bound to `127.0.0.1` on a
   free port, with a one-time user name and password and a fresh temporary certificate, and prints
   one JSON line back over SSH: port, user, password, certificate fingerprint.
4. Spark Connect forwards a local port to it over the same SSH connection (`-L`, on `127.0.0.1`
   only) and opens the viewer: on SparkOS, `sdl-freerdp` (or `xfreerdp`) with `/from-stdin` for the
   credentials (never on the command line) and `/cert:fingerprint:sha256:<fp>` so only that server
   is accepted; on Windows, `mstsc`, with the credentials stored by `cmdkey` for that one connection
   and deleted when it ends.
5. **While the screen is shared, the target shows a banner** that can't be hidden: "Your screen is
   being shared with <Owner> (seen / controlled)" with a **Stop** button. Stop, closing the viewer,
   or the SSH connection dropping ends `krdpserver` within a few seconds. Sessions also end after
   2 hours.

`--plasma` makes krdp use KWin's own screencast and fake-input protocols (granted to krdp by
`X-KDE-Wayland-Interfaces` in its desktop file) instead of the desktop portal. That matters: the
portal would show KDE's own "Allow remote control?" dialog, which nobody can answer on an
unattended machine. With `--plasma` the only gate is `spark-share`'s prompt, which we control.

### The sudo override

`spark-share request --no-ask` skips the prompt, and **only works as root** (it checks its effective
user and refuses otherwise). Spark Connect's **Take control without asking…** runs it through
`sudo -n`, like the restart button in part one: if sudo wants a password, nothing runs, and Spark
Connect opens a terminal with `ssh -t <host> sudo spark-share request --no-ask ...` typed for the
owner to run, then connects when that prints its JSON line. It never asks for, types or stores a
password.

Running as root also lets `spark-share` reach a session that belongs to **another user** than the
SSH login (find it with `loginctl`, start krdp in it with `systemd-run --machine=<user>@ --user`).
Without root, it can only share the login user's own session; asking for anyone else's says so.

The banner shows on an override too. On an empty machine it costs nothing, and on a machine with
someone at it, they should know.

**Plainly, in the README:** the prompt is consent for the person at the screen, not a security
wall. Anyone who already has SSH as the desktop's own user could start krdp themselves. What keeps
strangers out is the SSH key, as in part one.

### Seeing without control

The prompt and the banner say which one was asked for. Find out whether krdp can refuse input
(an option, or a config key in `krdpserverrc`); if it can, **See screen** uses it. If it can't,
ship only **Take control** for now and say so in the README, rather than a "view only" that isn't.

## Where `spark-share` lives

On the target, in the SparkOS image (`/usr/bin/spark-share`, a Python + Tk script in
`files/system/`), because the target machine must have it and the override runs it through
`sudo`. It's small, has no settings, and does nothing until called. Its prompt and banner follow
the house style and the system language (French or English), like the Spark apps.

This is the only part that goes into the image; Spark Connect itself stays optional. Add it to the
boot test only as `spark-share --self-test` (krdpserver and its desktop file are present, the
`--plasma` interfaces are granted), not a real share.

## Spark Connect changes

- Config: `desktop = true` on a machine shows **See screen**, **Take control** and **Take control
  without asking…** in its view. Machines without it (the servers) show nothing new.
  `machines.example.toml` gets one desktop machine with made-up names.
- The probe reports, for desktop machines only, whether someone is logged in to a graphical session
  and whether it is locked, so the card can say "Desktop: in use", "locked" or "nobody logged in",
  and the buttons can say up front that a prompt won't be answered.
- Each action's confirmation says what it will run and that the person at the machine will see a
  prompt (or, for the override, a banner and no prompt).
- An active session shows on the machine's card ("Screen shared, 12 min") with a **Stop** button.
- Alerts: none for screen sessions; they're started by the owner.

## Not in this part

- **Windows targets.** Windows 11 Home (the owner's Windows) has no RDP server, so a Windows target
  needs its own agent. Later, if the owner wants it.
- **The GestionDirecte tablets** stay on their own plan in [PLAN.md](../PLAN.md), "Remote care".
- **Machines outside the tailnet/LAN** (the hub and agent from part one's "Ready for later").
- A Spark-made viewer. The first version uses FreeRDP's window on SparkOS and `mstsc` on Windows.

## Tests

- **Unit:** the approval timeout and Deny; `--no-ask` refused without root; session lookup from
  fixture `loginctl` output (own user, another user, locked, none); the JSON line; Spark Connect's
  confirmation texts; the viewer command lines (no password in argv, certificate pinned); `mstsc`
  credentials removed after the session.
- **UI under Xvfb:** the prompt and the banner in English and French, no clipped text; Stop ends the
  session.
- **End to end in CI:** a headless KWin (`kwin_wayland --virtual`) session in a SparkOS container
  with sshd, a throwaway key and user. Request with an auto-allow test hook, see `krdpserver`
  listening on `127.0.0.1` only, connect with `xfreerdp /auth-only` through the forwarded port with
  the pinned certificate, then Stop and see the port closed. A request that times out starts
  nothing.
- **On the owner's PC:** only with the owner watching. Ask before the first real share.

## Done when

CI passes; the owner has shared one SparkOS desktop to Spark Connect, accepted the prompt, seen the
banner and stopped it; and has tried the override once with `sudo`. PR open for the owner.

## Open questions for the owner

1. **Which machines** have a desktop to reach today? If it's only this PC (from the laptop or the
   Windows side), the override matters less than if it's family or venue PCs.
2. **Venue laptop:** does it have a desktop and someone at it during events? If it runs Windows,
   it waits for the Windows agent.
