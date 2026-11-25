# Spark Clock: alarms, timers, stopwatch, world clocks

Optional Spark app. Not in the image; installs per user with `install.sh --user`, from Spark Store.

## Why

SparkOS has no clock app. An alarm that only works while its window is open is not an alarm, so the
point of this one is that the ringing does not depend on the window.

## What

- Alarms: time, days of the week (or once), label, sound, snooze (5, 9, 10, 15 minutes).
- Timers: several at once, labels, presets (buttons you can add or remove).
- Stopwatch with laps. World clocks, Montréal first.
- Ringing: a freedesktop notification with Stop and Snooze (+1 min for timers), plus a looping sound
  through PipeWire (`pw-play`; `paplay`, `gst-play-1.0` and `ffplay` as fallbacks).
- `spark-clock --timer 5m --label Tea` starts a timer from a terminal.

## How it rings with the window closed

The window only edits JSON files (`~/.config/spark-clock/clock.json`, and `timers.json`,
`stopwatch.json`, `commands.json` in `~/.local/state/spark-clock`). A separate process,
`spark-clock --daemon`, rings. It is a systemd user unit (`spark-clock.service`, `Restart=on-failure`)
that `install.sh --user` enables, so it starts at every login. It is a GLib main loop ticking every
second, single instance (flock), and writes a heartbeat the window reads to show "service on" or
"service off" (a TURN ON button starts it).

- Catch-up after sleep, a reboot or a crash: the service saves its last tick. An alarm or timer that
  came due while it was off still rings if it is less than 10 minutes late (and says how late);
  older ones become a "missed" notice, so nothing rings hours late.
- Alarms use local time, so a daylight saving change does not move them. Timers use real time.
- The window answers a ring through `commands.json` (stop, snooze, +1 min); the notification's
  buttons and a dismissed notification (counts as stop) go straight to the service.

## Decisions

- **Wake from suspend (0.2.0), opt in.** A setting "Wake the PC from sleep", off by default. The
  service arms one wake time (the next enabled alarm or waiting snooze, a minute early) and moves it
  when alarms change and after each ring. Root part: `/usr/libexec/spark-clock-wake` run through
  pkexec, with a polkit action `dev.wolklaw.SparkClock.wake` (`allow_active` yes, no password).
  It only sets or clears one systemd timer, `spark-clock-wake-<uid>`, with `WakeSystem=true` that
  runs `/usr/bin/true`, for a 10 digit epoch 10 s to 8 days ahead; uid from `PKEXEC_UID`;
  no shell, absolute paths, fixed environment (same hardening as Spark Firewall's helper).
  Why a systemd timer and not `/sys/class/rtc/rtc0/wakealarm`: systemd already owns the RTC alarm
  for its own timers, and a second writer would fight it. A transient timer also vanishes at reboot.
  The helper and policy ship in the image (`files/scripts/spark-clock-wake.sh`, in the Containerfile).
  The script is deliberately not `spark-clock.sh`: that name would make Spark Store treat Clock as
  built in. Version 0.2.0 raises `system_api` to 2, so older live bundles stop matching the image.
  Without the helper (older image) the option says it is unavailable and nothing is called.
  It cannot wake a PC that is shut down, and hibernate depends on the firmware. Timers do not wake.
- **Sounds are generated**, by `make_sounds.py` (stdlib `wave` and `math`, fixed seed), so they are
  original and need no third-party licence. THIRD-PARTY.md has no entry for this app because nothing
  here is third-party.
- Time zones come from the system's tz database (`zoneinfo`); Montréal is `America/Toronto`.

## Status

Built 2026-11-24 in [files/spark-clock](../files/spark-clock), version 0.1.0; wake from suspend added in 0.2.0. Optional, not in the
image. See the PR for what was tried on the real PC and what only ran with fakes.

- Tests: schedule (including the spring daylight saving change), store, engine with a fake clock,
  notifier and sound, the sound loop with a fake player, and the window under a display, in English
  and French with a text-fit check.
- Wake: tests cover the scheduling logic, the engine hook and the helper's input checks, all with
  fake runners (no systemd, RTC, pkexec or polkit).
- Not covered by tests: the real notification buttons being clicked, and sound heard by a person.
  Also not tried on a booted SparkOS: pkexec from the user service (polkit must treat the service as
  the active local user), the timer really waking the PC, and the PC staying up until the alarm.
- No screenshot was checked by eye from the owner's Plasma session: its Xwayland windows capture as
  blank. The window was checked for clipped text under a display instead.
