# First day on SparkOS

What to do after [install.md](install.md), in order. It takes about an hour, most of it downloads.

## 1. Get the latest SparkOS (5 minutes)

The installer was rebuilt on 21 November at 3 AM with every fix so far (Spark Media's one window,
media keys and HEIC photos; Spark Archive's Windows-compatible password zips; FreeSuite opening from
the menu). SparkOS also builds a new version every day, so check once:

Open **Spark Update** from the menu and press **Check now**. If it says you're up to date, there's
nothing to do. If it downloads a new version, wait until it says it's ready, then **Restart to update**.

## 2. Spark Welcome

It opens by itself at the first sign-in (later: menu > Spark Welcome).

- **Apps:** tick the launchers you use. For World of Warcraft that's **Lutris** (Battle.net runs through it).
- **Files from Windows:** pick your Windows drive and the folders to copy (Desktop, Documents, Pictures...).
  It only reads the Windows drive, never writes to it. If it says the drive is hibernated, Fast Startup
  was still on: start Windows, turn it off (install.md, "Before", step 3), shut down, and try again.
- **Checks:** graphics, sound, printer and network. Anything it flags, note it for the day-one list below.

## 3. FreeSuite

FreeSuite opens from the menu like any app (checked on a real Plasma desktop in every build). If it
ever starts without showing a window, start it from Konsole instead:

```bash
/usr/lib/opt/freesuite/freesuite --ozone-platform=x11
```

(Why: FreeSuite waits to be painted before it shows its window, and Plasma's native Wayland never paints
a hidden window. SparkOS starts it through XWayland until a FreeSuite release fixes it; the fix is made
and waiting for your OK to release.) Then sign in to your mail as on Windows.

## 4. World of Warcraft with your interface as it is

Your interface lives in two folders of the Windows install: `WTF` (settings, key bindings, addon
settings, 7 MB) and `Interface` (addons, about 930 MB). Copy them and nothing needs redoing.

1. **Lutris** (installed in step 2): search "Battle.net", install it with the official script, sign in,
   install World of Warcraft. (Battle.net under Lutris is Wine; it works for WoW.)
2. **Don't start WoW yet.** Quit Battle.net.
3. Open **Dolphin**. Your Windows "Games" drive is under **Devices** on the left; click it to open it
   (it may ask for your password). Go to `Battle.Net/World of Warcraft/_retail_/`.
4. Copy `WTF` and `Interface` into the new install's `_retail_` folder, replacing what's there. With
   Lutris's script that is usually
   `~/Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/`. If it isn't, Battle.net
   shows the real folder: WoW's gear icon > **Show in Explorer**.
5. Start WoW from Battle.net (Spark Games lists Battle.net, through Lutris). Your bars, binds
   and addons are there.

The Windows copy of WoW stays on E: untouched, so Windows still has it too.

## 5. Day-one checks (things only your hardware can tell)

Note anything that doesn't work and it gets fixed in an update.

- [ ] The SparkOS boot splash and the sign-in screen look right on your monitor.
- [ ] **Ctrl+Shift+Esc** opens Spark Monitor. **Print Screen** starts Spark Snip.
- [ ] Spark Scan finds the Canon TR4700 over Wi-Fi and scans a page.
- [ ] Spark Link pairs with your phone.
- [ ] A game in Steam (from the Store) runs, with the RX 6800 XT (Spark Monitor's Performance tab shows the GPU).
- [ ] An Xbox or PlayStation controller works in Spark Games' big-screen mode.
- [ ] Double-click an `.exe` installer: Spark Run offers to install it.
- [ ] Spark Media: play a song, press the keyboard's play/pause key, open a phone photo.
- [ ] Dolphin's right-click menu has Extract and Compress (Spark Archive).
- [ ] Spark Update's notification appears after the next update is downloaded.

## If something goes wrong

- **Back to Windows:** F8 at the ASUS logo > Windows Boot Manager.
- **A bad update:** at startup, pick the previous version in SparkOS's boot menu, or Spark Update >
  Roll back. Nothing is deleted.
- **An app won't open:** run it from Konsole (its command is its name, like `spark-media`) to see the error.
