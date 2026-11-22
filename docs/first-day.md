# First day on SparkOS

What to do after [install.md](install.md), in order. It takes about an hour, most of it downloads.

## 1. Get the latest SparkOS (5 minutes)

SparkOS builds a new version every day, and the installer can be older than that. Open
**Spark Update** from the menu and press **Check now**. If it says you're up to date, there's
nothing to do. If it downloads a new version, wait until it says it's ready, then
**Restart to update**.

## 2. Spark Welcome

It opens by itself at the first sign-in (later: menu > Spark Welcome).

- **Games:** tick the launchers you use: Steam, Heroic (Epic, GOG, Amazon), Lutris (Battle.net,
  EA app, Ubisoft Connect). Your games and their licences stay in those accounts: sign in to each,
  and **Spark Games** then shows everything they installed in one library.
- **Apps:** Discord, Signal, Spotify, OBS and others from Flathub. Services with no Linux app, such
  as Amazon Music, are added as a menu entry that opens their web player in your browser.
- **Files from Windows:** pick the Windows drive, then the folders. Spark Welcome reads where
  Windows really keeps each one (OneDrive, or another drive), and shows each folder's Windows path
  so you can check it. It opens your drives read-only and never writes to them; it may ask for
  your password once per drive. If it says the drive is hibernated, Fast Startup was still on:
  start Windows, turn it off (install.md, "Before", step 3), shut down, and try again.
- **Checks:** graphics, sound, printers and network. Printers on your network are usually found by
  themselves (driverless printing).

## 3. FreeSuite

FreeSuite (mail, documents, spreadsheets, slides, PDF) opens from the menu like any app, with all
its apps already installed. Sign in to your mail as on Windows.

## 4. A Windows game with its settings (World of Warcraft as the example)

A game's settings and add-ons usually sit in its install folder, so they come along with a copy.
For World of Warcraft that's `WTF` (settings, key bindings, add-on settings) and `Interface`
(add-ons), in the `_retail_` folder.

1. In **Lutris** (installed in step 2): search "Battle.net", install it with the official script,
   sign in, install the game. Don't start it yet; quit Battle.net.
2. Open **Spark Files** (the folder icon on the dock). Your Windows drives are under **Drives**
   on the left as C:, D: and so on; click one to open it. Find the game's folder, for example
   `World of Warcraft/_retail_/`.
3. Copy `WTF` and `Interface` into the new install's `_retail_` folder, replacing what's there.
   With Lutris's script that is usually
   `~/Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/`. If it isn't,
   Battle.net shows the real folder: the game's gear icon > **Show in Explorer**.
4. Start the game from Battle.net or from Spark Games.

**To skip the big download:** in step 1 install only Battle.net. Copy the whole game folder from
the Windows drive into `~/Games/battlenet/drive_c/Program Files (x86)/`, then on the game's page
in Battle.net click **Locate the game** and pick that folder. Battle.net checks the files and
updates what it needs.

## 5. Day-one checks (things only your hardware can tell)

- [ ] The boot splash and the sign-in screen look right on your monitor.
- [ ] **Ctrl+Shift+Esc** opens Spark Monitor. **Print Screen** starts Spark Snip.
- [ ] Spark Scan finds your scanner and scans a page.
- [ ] Spark Link pairs with your phone (Soot for Android: **Link to PC**).
- [ ] A Steam game runs, and Spark Monitor's Performance tab shows the GPU.
- [ ] A game controller works in Spark Games' big-screen mode.
- [ ] Double-click a Windows `.exe` installer: Spark Run offers to install it.
- [ ] Spark Media plays a song, the keyboard's play/pause key works, a phone photo opens.
- [ ] Spark Files opens your folders and Windows drives, and its right-click menu has Extract and
      Compress (Spark Archive).
- [ ] "Show in folder" in Soot's downloads opens Spark Files with the file selected.
- [ ] Spark Update's notification appears after the next update is downloaded.

## If something goes wrong

- **Back to Windows:** your firmware's boot menu key at power-on > Windows Boot Manager.
- **A bad update:** at startup, pick the previous version in SparkOS's boot menu, or Spark Update >
  Roll back. Nothing is deleted.
- **An app won't open:** run it from Konsole (its command is its name, like `spark-media`) to see
  the error.
