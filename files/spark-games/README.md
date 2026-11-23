# Spark Games

One library for every game installed on the computer, whatever launcher it came from. Spark Games reads what Steam (including non-Steam shortcuts), Heroic (Epic, GOG, Amazon), Lutris, the itch app, Bottles, the Minecraft launcher and Prism Launcher have installed, adds the programs you add yourself, and starts each game through the launcher that owns it. It never changes the launchers' files. It is not a store: you buy games on each company's site. But it can sign in to Epic, GOG and Amazon itself, list what you own, and install, update, verify, uninstall and start those games (see [Stores and launchers](#stores-and-launchers)), so Heroic and Lutris are no longer needed.

It ships in SparkOS (the image build runs [files/scripts/spark-games.sh](../scripts/spark-games.sh), which runs `install.sh --deps`). It can also install for one user with no root, which the future Spark Portal can use (see below).

- **Library:** covers or a list, most recently played first (or A–Z), search as you type, a filter per store. Each game shows its cover, store and playtime.
- **Game page:** big cover, launcher, playtime, last played, install folder (opens in Dolphin), and Play.
- **MangoHud and GameMode:** for games you added, two switches that Spark Games applies when it starts them. Steam games go through Steam's launch options, which Spark Games doesn't touch, so it shows the line to paste (`MANGOHUD=1 gamemoderun %command%`) with a Copy button. For Heroic and Lutris games it says to use those apps' own settings.
- **Your own games:** "Add a game" takes a Linux program or a Windows `.exe`. Windows games run with Proton through `umu-run`. Without `umu-run` it says so and offers Bottles' Flathub page (Bottles is a separate project).
- **Playtime:** each launcher's own count. Games started from Spark Games are also recorded in `~/.local/share/spark-games/playtime.json`, so your own games get playtime too.
- **Anti-cheat warning (online, can be turned off):** downloads the public [AreWeAntiCheatYet](https://areweanticheatyet.com) list at most once a week and marks installed games listed as Denied or Broken. Offline with no saved copy, nothing is shown. Nothing about your games is sent.
- **No launcher yet:** says so, and offers Spark Welcome (if installed) or the Store.
- **Controller:** the D-pad or left stick moves (held, it repeats), A plays, B goes back, Y searches, Start opens the game page, LB/RB change the store filter, Guide/Home opens the big screen. Read only while the Spark Games window is in front (see [Controllers](#controllers)).
- **Big screen:** a fullscreen couch layout made to read from across the room: the selected game large at the top, rows of big covers below (Keep playing, one row per launcher, All games), what each button does along the bottom, a game page, and an on-screen keyboard for search. Open it with the header's fullscreen button, F11, the Guide button, `spark-games --big-screen`, or the menu entry's "Big screen" action. Esc or B leaves it.
- **French:** every word in French when the PC's language is French (`LC_ALL`, then `LC_MESSAGES`, then `LANG` starting with `fr`). `SPARK_LANG=en` or `SPARK_LANG=fr` overrides it.

| Key | Library | Game page | Big screen | Controller |
|---|---|---|---|---|
| Arrows, Page Up/Down, Home/End | move | | move; Page Up/Down change row | D-pad, left stick |
| Enter | play the selected game | play | play | A |
| Space or I | open its page | | open its page | Start |
| / or start typing | search | | search (on-screen keyboard) | Y |
| Esc | clear the search | back | close, clear the search, then leave | B |
| F11 | big screen | big screen | leave | Guide |
| F5 | scan again | scan again | scan again | |
| | store filter | | change row | LB / RB |

## Where it looks

| Launcher | Flatpak (SparkOS's usual one) | Regular install | Started with |
|---|---|---|---|
| Steam | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` | `~/.local/share/Steam`, `~/.steam/steam` | `flatpak run com.valvesoftware.Steam steam://rungameid/<appid>` or `steam steam://rungameid/<appid>` |
| Heroic | `~/.var/app/com.heroicgameslauncher.hgl/config/heroic` | `~/.config/heroic` | `xdg-open heroic://launch/<runner>/<appName>` |
| Lutris | `~/.var/app/net.lutris.Lutris/data/lutris` | `~/.local/share/lutris` | `flatpak run net.lutris.Lutris lutris:rungameid/<id>` or `lutris lutris:rungameid/<id>` |
| itch | `~/.var/app/io.itch.itch/config/itch` | `~/.config/itch` | `~/.itch/itch-setup --appname itch --run-game <id>` when it's there, otherwise `xdg-open itch://install?game_id=<id>&launch` (the itch app asks to confirm) |
| Bottles | `~/.var/app/com.usebottles.bottles/data/bottles/bottles` | `~/.local/share/bottles/bottles` | `flatpak run --command=bottles-cli com.usebottles.bottles run -b <bottle> -p <program>` or `bottles-cli run ...` |
| Minecraft Launcher | `~/.var/app/com.mojang.Minecraft/.minecraft` | `~/.minecraft` | `flatpak run com.mojang.Minecraft` or `minecraft-launcher` |
| Prism Launcher | `~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher` | `~/.local/share/PrismLauncher` | `flatpak run org.prismlauncher.PrismLauncher --launch <instance>` or `prismlauncher --launch <instance>` |

- **Steam:** `steamapps/libraryfolders.vdf` for every library folder, `appmanifest_<appid>.acf` for installed games, covers from `appcache/librarycache/`, playtime and last played from `userdata/<id>/config/localconfig.vdf`. Proton, the Steam Linux Runtimes and redistributables are left out (known IDs and names, or a `toolmanifest.vdf` in their folder), and so are games still downloading.
- **Steam shortcuts:** non-Steam games added to Steam, from each account's `userdata/<id>/config/shortcuts.vdf` (binary VDF), with the cover you set in Steam (`config/grid/<id>p.*`) and the last-played time. They start through Steam (`steam://rungameid/<64-bit id>`). Hidden shortcuts are left out, and so are shortcuts that start another launcher Spark Games already lists (Heroic's, Lutris's and Bottles' "add to Steam", Prism, itch), so a game doesn't show twice.
- **itch:** `db/butler.db` opened read-only: installed copies (`caves`), their game (`games`) and folder (`install_locations`), time played and last played. Tools, asset packs, soundtracks, comics and books are left out. No covers yet (the itch app doesn't keep them as files Spark Games can find).
- **Bottles:** each bottle's `bottle.yml`, the programs you added to it (`External_Programs`). Removed programs are left out. Bottles keeps no playtime and no covers Spark Games reads.
- **Minecraft Launcher:** one entry, "Minecraft: Java Edition", when `launcher_profiles.json` exists; last played is the newest `lastUsed` of its profiles. The launcher records no playtime.
- **Prism Launcher:** one entry per instance (`instances/<id>/instance.cfg`, or the folder `InstanceDir` in `prismlauncher.cfg` points to), with its time played, last launch and icon.
- **Heroic:** the installed-games JSON of each store (`legendaryConfig`, `gog_store`, `nile_config`), titles and art from its library caches, covers Heroic already downloaded to `images-cache/`, playtime from `store/timestamp.json`. DLC is left out.
- **Lutris:** `pga.db` opened read-only; covers from `coverart/` or `banners/`. Games Lutris runs through Steam are left out, since Steam lists them.
- **Your own:** `~/.config/spark-games/games.json`.

A missing launcher isn't an error; its games just don't appear. A file in a format Spark Games doesn't understand is logged and skipped, and the other launchers still show.

## Stores and launchers

Settings, then "Accounts and launchers" opens the Stores view.

**Accounts.** Epic, GOG and Amazon each have a Sign in button. Spark Games opens the company's own login page. If WebKitGTK is installed it shows the page in its own window and reads the code itself. If not, or if that window fails, it opens your browser and you paste what the page ends on (Epic: the page's text, which holds `authorizationCode`; GOG and Amazon: the address of the last page). The paste always works. Sign out removes the saved token. Tokens are in `~/.config/spark-games/accounts/`, folders `0700`, files `0600`, and are never written to the log.

**Store programs.** The work is done by three GPL-3.0 programs, started as separate processes and never imported: [legendary](https://github.com/legendary-gl/legendary) (Epic) 0.21.1, [gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl) (GOG) 1.4.0 and [nile](https://github.com/imLinguin/nile) (Amazon) 1.2.0. They are not in the image. The first time one is needed Spark Games downloads that exact release into `~/.local/share/spark-games/runners/`, checks its SHA-256 (the same way Spark Run downloads Wine) and deletes it if it does not match. A copy in `/usr/lib/spark-games/runners/` is used when present, and `SPARK_GAMES_LEGENDARY`, `SPARK_GAMES_GOGDL` and `SPARK_GAMES_NILE` point at another build. Versions, links and checksums: [THIRD-PARTY.md](../../THIRD-PARTY.md). `--self-test` lists which are present and their versions.

| | Epic | GOG | Amazon |
|---|---|---|---|
| Program | legendary | gogdl | nile |
| Owned list | `legendary list --json` | the account's product list, read with the token gogdl saved | `nile library sync` and `nile library list --json` |
| Install, update, verify | yes | yes (update and verify both run `gogdl update/repair`) | yes |
| Update detected | yes (the installed build differs from the one in `legendary list --json`) | no, see Known gaps | yes (`nile list-updates`) |
| Cloud saves | per-game switch, `legendary sync-saves` before and after | not supported | not supported |
| Started with | `legendary launch --json`, then the command it prints through umu-run | `gogdl launch` through umu-run (Linux builds start directly) | `nile launch` through umu-run |

- **Owned games** are listed greyed, with an Installed / All owned filter (Installed is the default and is remembered). The list is cached in `~/.cache/spark-games/owned-<store>.json`, refreshed at most once a day and on F5, and covers are fetched once. An owned game that is installed (by Spark Games or Heroic) shows once.
- **Install, update, verify** run in a helper process (`spark-games --job`) so the window can close. The game page shows progress, speed and time left, with Pause (SIGSTOP the client), Resume and Cancel. One install runs per disk; the others show "Waiting for another install on this disk". Before installing it asks the store for the download and disk size and compares it with the free space. Games go in `~/Games/<store>/` unless you pick a folder (Settings key `games_dir`).
- **Uninstall** deletes the game's folder only if Spark Games installed it and the folder is inside the folders it installs into. A game taken over from Heroic is only forgotten, and its files stay.
- **Starting a game** goes through Spark Games: Proton through `umu-run` (UMU-Proton, or GE-Proton with a per-game switch), MangoHud and GameMode switches as for your own games, a Wine folder per game in `~/.local/share/spark-games/prefixes/`. Spark Games never logs the launch command, since Epic's holds a session token.
- **Taking over Heroic.** On first start, if Heroic installed games, Spark Games asks once whether to use them. Nothing is downloaded again and nothing of Heroic's is changed or deleted: Epic games are handed to legendary with `import --disable-check`, GOG games are recorded in place, Amazon games go through `nile import`. Heroic's Wine folders are not reused (Heroic's Proton is not the one Spark Games starts the game with); the game gets its own. Games Heroic still lists are hidden once taken over, so none shows twice. The Stores view has a button to ask again.

### On both images

The same code runs on `ghcr.io/wolklaw/sparkos` (Bazzite base) and `ghcr.io/wolklaw/sparkos-fedora` (plain Fedora Kinoite). `umu-run` is in both (on Fedora from Terra). The three store programs are single downloaded files that need nothing from either base's packages. Neither image installs WebKitGTK (`docs/fedora-base.md` lists it as dropped), so on both the sign-in uses the paste way; the window is only used where WebKitGTK happens to be installed. CI runs the in-image check (`install.sh --user`, `--self-test`, uninstall, and a report of `umu-run` and WebKitGTK) for both images.

### Added launchers

Battle.net, EA app, Ubisoft Connect and Rockstar Games Launcher each have an Add button. Spark Games downloads the installer from the company's own address (HTTPS, a fixed list of hosts that a redirect must also stay on, 500 KB to 400 MB, must start with `MZ`), logs its SHA-256, and runs it through `umu-run` in `~/.local/share/spark-games/prefixes/<launcher>`; the installer's window opens for you to finish. The companies replace these installers in place, so unlike the store programs they **cannot** be checked against a fixed checksum, and the game IDs umu uses for them (`umu-<launcher>`) are placeholders, not entries from umu's database. The launcher then has its own tile. If Lutris already installed one, "Use Lutris's" takes it over without copying or moving it; Spark Games starts it with its own Proton, which can change that Lutris folder, and the confirmation says so. Removing a launcher deletes only a folder Spark Games made. Lutris's own tile for it is hidden.

## Speed

- The library from the last run (`~/.cache/spark-games/library.json`) shows at once; launchers are scanned again in a background thread.
- Covers are cut once to the tile size with Pillow and cached in `~/.cache/spark-games/covers/`. Only the rows on screen are drawn, so 500 games scroll like 5.
- No polling. When the window gets focus, it compares the modification times of the launchers' files with the last scan and scans again only if something changed.
- When you press Play, a small helper process (`spark-games --track`) starts the game and records the session, so the window can stay open, minimize or close (Settings). For your own games the helper waits for the program to exit. For launcher games it looks every 10 seconds for a process running from the game's folder (it reads `/proc` only).
- Controllers don't poll either (next section). The big screen draws only the covers in view and does nothing while nobody touches it.

## Controllers

Spark Games reads controllers straight from the kernel (evdev) with Python's standard library, so it needs no extra package: `/sys/class/input/event*/device/capabilities/key` says which devices are gamepads (they have the A button, `BTN_SOUTH`), and their events come from `/dev/input/event*`, which the logged-in user can read on SparkOS (udev's `uaccess`). Devices are never grabbed, so Steam and games still see them.

- **Only while the window is in front.** When Spark Games has focus, each controller's device and an inotify watch on `/dev/input` go into Tk's event loop, so the app wakes only when a button moves or a controller is plugged in. When it loses focus, everything is closed: no wake-ups while a game runs, and buttons meant for the game don't reach the library. The Guide button therefore opens the big screen only while Spark Games is in front; while you play, Steam keeps its own use of it.
- **Plugged in later:** the inotify watch sees the new device; Spark Games opens it a quarter second later, once udev has given access, and says "CONTROLLER: <name>" in the status line. Settings lists the controllers being read.
- **Layouts:** Xbox pads report X and Y the other way round from PlayStation pads, so both top buttons (Y and X, triangle and square) search. The stick's range comes from the driver (xpad: −32768 to 32767, PlayStation: 0 to 255); it counts as a press past 55 % and lets go under 35 %. A held direction repeats after 0.4 s, every 0.11 s.

## Files

Settings in `~/.config/spark-games/` (`config.json`, `games.json`), playtime in `~/.local/share/spark-games/`, cache in `~/.cache/spark-games/`, log in `~/.local/state/spark-games/`. Windows games you add get their own Wine prefix in `~/.local/share/spark-games/prefixes/`. Store accounts: `~/.config/spark-games/accounts/` (owner only). Store state: `stores.json` (installed store games and added launchers) and `jobs/` in the data folder; the owned lists in the cache folder.

## Install, run, test

```
sudo bash install.sh --deps                # system-wide with Fedora packages (what the image build runs)
bash install.sh --user                     # for you only, no root: ~/.local/lib/spark-games, ~/.local/bin/spark-games, menu entry, icons
bash install.sh --user --uninstall         # remove exactly what that installed (settings and playtime stay)
python3 spark_games.py                     # run from this folder
python3 spark_games.py --big-screen        # start in the big screen
SPARK_LANG=fr python3 spark_games.py       # in French, whatever the PC's language
python3 spark_games.py --self-test         # parsers against the bundled fixtures, a recorded controller, Pillow, xdg-open; no display, no network
SPARK_GAMES_HOME=/some/fake/home python3 spark_games.py    # scan another folder instead of your home (for testing)
python3 -m unittest discover -s tests -v
python3 make_icons.py                      # redraw icons/ after changing the mark
```

On SparkOS, `--user` needs nothing extra: Python 3, Tk and Pillow are in the image. `spark-app.json` describes the app for the future Spark Portal (ID, version, size, what it needs and reads).

The tests use the fixtures in `tests/fixtures/`: a fake home with a Flatpak Steam (two library folders, Proton, a redistributable, a tool found by its `toolmanifest.vdf`, a game still downloading, a hand-written manifest with escaped quotes, and a binary `shortcuts.vdf` with a current shortcut, an old one with no app ID, one Heroic added and a hidden one), a Flatpak Heroic with one game per store and a DLC, a regular Lutris (`pga.db` is built from `pga.sql`), a regular itch app (`butler.db` built from `butler.sql`, with an asset pack to leave out), a Flatpak Bottles (a removed program, an empty bottle), the official Minecraft launcher, and Prism with two instances and a temp folder. Covers are drawn by the tests, so no art is copied in.

Controllers are tested with recordings in evtest's format (`tests/fixtures/gamepad/`: an Xbox pad and a DualSense). uinput isn't available in CI, so on Linux the tests play them through a FIFO standing in for `/dev/input/eventN`, with a fake `/sys/class/input`, and the real reader picks them up from Tk's event loop: every button, held directions repeating, a controller plugged in and pulled out later, a device that can't be read until its permissions change, and nothing open while the window is in the background. A further test measures the process's CPU time over 3 s idle with the controller watch on, off, and in the big screen (under 0.15 s each). The big screen is checked at 1920×1080 under Xvfb: its rows, moving, the game page, the on-screen keyboard, leaving it, and no text under 20 px. CI ([workflow](../../.github/workflows/spark-games.yml)) runs everything under Xvfb in Fedora. Inside the published SparkOS image it runs the image build step as root followed by `--self-test`, then installs it with `--user` as a normal user, runs `--self-test` and uninstalls it.

## Known gaps

- Not tried with real Steam, Heroic, Lutris, itch, Bottles, Minecraft or Prism libraries yet; only with the fixtures. Heroic's file layout changes between versions, so its covers and playtime are the most likely to need fixing; the itch database columns come from butler's source, not a real `butler.db`.
- Controllers are tested only with recorded events, not a real controller. Not checked yet: Steam running at the same time (if Steam Input turns the controller into keyboard and mouse on the desktop, a button could act twice), Nintendo and 8BitDo layouts, and Bluetooth pads.
- The Guide button opens the big screen only while Spark Games is in front (by design, see Controllers).
- No covers for itch, Bottles and the official Minecraft launcher.
- The playtime helper for launcher games finds the game by its install folder on the command line. A game started some other way (a launcher stub elsewhere) may not be counted; the launcher's own playtime is still shown.
- MangoHud and GameMode switches only apply to games you added. For the other launchers, use their own settings.
- **Stores and launchers were built without a real account or the real programs.** legendary, gogdl and nile were never run during development: the tests use fake clients that print recorded output, so the exact output formats, the Epic and Amazon sign-in, the GOG product list endpoint (`embed.gog.com`, read with gogdl's token) and GOG cover addresses are unverified against the real services. Not done yet, each for the owner to try on a real PC:
  - [ ] Sign in to Epic by paste, and with the WebKitGTK window.
  - [ ] Sign in to GOG and to Amazon.
  - [ ] Install a small free game from one store, pause, resume, cancel, then finish it and start it.
  - [ ] Take over one Heroic game and confirm Heroic still works with it.
  - [ ] Add one launcher (Battle.net) and start it.
- The WebKitGTK sign-in window (`signin_window.py`) has not been run: the image has no WebKitGTK, and WebKitGTK is optional. Without it only the paste way is used.
- While legendary, gogdl or nile checks a sign-in code, the code is in their command line, so other programs of your own user can see it in the process list for a moment. The window says so. It is used once and expires.
- GOG: no update detection (gogdl has no cheap check), and no cloud saves. Amazon: no cloud saves. GOG and Amazon games are updated with Update, which you choose yourself.
- The added launchers' installers have no checksum (see above), and their game IDs are placeholders, so Proton may apply fewer fixes than umu's database would.
- The owned list is Windows and Linux only; Mac-only games are left out.
