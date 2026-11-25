# Spark session: polkit agent, sign-in screen, lock screen

Stage 3 of "Replacing KDE" in [PLAN.md](../PLAN.md), the security-sensitive part. Source and
details: [files/spark-session](../files/spark-session/README.md). Not an app: it ships in the
image and changes only with the image.

## What is built

- **`spark-polkit`**: the polkit authentication agent for the Spark session. House-style dialog,
  English and French, never logs the password. Nothing starts it yet; the Spark shell's session
  script does (below).
- **`spark-greeter`**: the sign-in screen for greetd, run by KWin as a bare compositor. Installed
  and **off**. `spark greeter enable|disable|status` is the opt-in and the rollback. greetd is in
  the image but not enabled and is not the display manager.
- **Lock screen: not built.** KWin 6.8.3 has no `ext_session_lock_manager_v1`, so the Spark
  session keeps kscreenlocker. The README says what a Spark lock needs once KWin has it. CI
  prints a notice the day KWin gains the protocol.

## For the Spark shell agent: lines for the `spark` session script

```
# once the compositor is up, before the shell
export XDG_CURRENT_DESKTOP=Spark      # anything but KDE, or polkit-kde's autostart runs too
/usr/bin/spark-polkit &               # exits 1 with a message if another agent is registered
```

Lock screen: keep kscreenlocker (`kwin_wayland` without `--no-lockscreen`). Do not pass
`--no-lockscreen` in the Spark session. The greeter session script uses it because the sign-in
screen must not be lockable.

## What the owner should try on real hardware

Nothing here has run on real hardware. In this order:

1. **Polkit agent, safe.** In the Spark session (once the shell agent wires it), run
   `pkexec true`. A Spark dialog should ask for your password; a wrong password says so and asks
   again; Cancel closes it. Also try a Settings change that asks for a password. Try it in French
   (`SPARK_LANG=fr spark-polkit`).
2. **Lock screen.** In the Spark session, lock (Meta+L). Unlock with the password. Kill
   `kscreenlocker_greet` from a TTY; the screen must stay locked (it did in headless KWin, but
   it was not restarted there within 10 s, so check whether it comes back).
3. **Sign-in screen, last, and only with a way back.**
   - Check the way back first: Ctrl+Alt+F3 shows a login prompt and you know your password there.
   - `spark greeter status`, then `spark greeter enable`, then restart.
   - Try: the right user is selected, the password works, the session list has Plasma and Spark,
     a wrong password says so, the sleep, restart and shut down buttons work, both layouts of
     your keyboard type correctly. Also try with the monitors you use (mixed refresh, HDR on).
   - Unknowns I could not test: SELinux denials for greetd (look at `ausearch -m avc -ts recent`),
     whether KWin gets the GPU as the `greetd` user (video and render groups), whether the
     sign-in screen shows on every monitor, and that the fallback unit fires.

### Rollback

- `spark greeter disable`, then restart. Plasma Login Manager signs you in again.
- If the screen shows nothing: Ctrl+Alt+F3, sign in, `spark greeter disable`, restart.
- Automatic: four failed starts of greetd in a minute make systemd run
  `spark-greeter-ctl auto-rollback`, which switches back and starts Plasma Login Manager.
- Last resort: pick the previous deployment in the boot menu.

## What was tried

**Really** (real software, in containers, never on this PC): the polkit agent registering with a
real polkitd and handling a request; greetd's real IPC against a real greetd with PAM; the greeter
window under Xvfb in English and French; the enable and disable helper in a fake root; headless
KWin 6.8.3 with kscreenlocker locking and surviving a killed lock process.

**With fakes**: the agent against a dbusmock authority; the greeter against a fake greetd; the
helper against a fake `systemctl`.

**Nobody**: anything on real hardware: a real GPU, real monitors, SELinux, logind, a real login
through greetd, the fallback unit firing, the polkit `pkcheck` round trip (polkitd needs logind
sessions; it skips in a container), the dialog on a real compositor, kscreenlocker's greeter
restarting after a crash.

## Changes from the brief

- No `spark-lock`: KWin has no ext-session-lock (see above).
- The `spark` session script is not touched; it belongs to the Spark shell branch. The lines to add
  are above.
- Commit trailer says Sonnet 5.5, the model that wrote it, not Opus 5.5 as the brief said.
