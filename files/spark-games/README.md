# Spark Games

One library for every game installed on the computer, whatever launcher it came from. Spark Games reads what Steam, Heroic (Epic, GOG, Amazon) and Lutris have installed, adds the programs you add yourself, and starts each game through the launcher that owns it. It never changes the launchers' files, and it is not a store: buying, downloading, updates, cloud saves and friends stay in each launcher.

It ships in SparkOS (the image build runs [files/scripts/spark-games.sh](../scripts/spark-games.sh), which runs `install.sh --deps`). It can also install for one user with no root, which the future Spark Portal can use (see below).

- **Library:** covers or a list, most recently played first (or A–Z), search as you type, a filter per store. Each game shows its cover, store and playtime.
- **Game page:** big cover, launcher, playtime, last played, install folder (opens in Dolphin), and Play.
- **MangoHud and GameMode:** for games you added, two switches that Spark Games applies when it starts them. Steam games go through Steam's launch options, which Spark Games doesn't touch, so it shows the line to paste (`MANGOHUD=1 gamemoderun %command%`) with a Copy button. For Heroic and Lutris games it says to use those apps' own settings.
- **Your own games:** "Add a game" takes a Linux program or a Windows `.exe`. Windows games run with Proton through `umu-run`. Without `umu-run` it says so and offers Bottles' Flathub page (Bottles is a separate project).
- **Playtime:** each launcher's own count. Games started from Spark Games are also recorded in `~/.local/share/spark-games/playtime.json`, so your own games get playtime too.
- **Anti-cheat warning (online, can be turned off):** downloads the public [AreWeAntiCheatYet](https://areweanticheatyet.com) list at most once a week and marks installed games listed as Denied or Broken. Offline with no saved copy, nothing is shown. Nothing about your games is sent.
- **No launcher yet:** says so, and offers Spark Welcome (if installed) or the Store.

| Key | Library | Game page |
|---|---|---|
| Arrows, Page Up/Down, Home/End | move | |
| Enter | play the selected game | play |
| Space or I | open its page | |
| / or start typing | search | |
| Esc | clear the search | back |
| F5 | scan again | scan again |

## Where it looks

| Launcher | Flatpak (SparkOS's usual one) | Regular install | Started with |
|---|---|---|---|
| Steam | `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` | `~/.local/share/Steam`, `~/.steam/steam` | `flatpak run com.valvesoftware.Steam steam://rungameid/<appid>` or `steam steam://rungameid/<appid>` |
| Heroic | `~/.var/app/com.heroicgameslauncher.hgl/config/heroic` | `~/.config/heroic` | `xdg-open heroic://launch/<runner>/<appName>` |
| Lutris | `~/.var/app/net.lutris.Lutris/data/lutris` | `~/.local/share/lutris` | `flatpak run net.lutris.Lutris lutris:rungameid/<id>` or `lutris lutris:rungameid/<id>` |

- **Steam:** `steamapps/libraryfolders.vdf` for every library folder, `appmanifest_<appid>.acf` for installed games, covers from `appcache/librarycache/`, playtime and last played from `userdata/<id>/config/localconfig.vdf`. Proton, the Steam Linux Runtimes and redistributables are left out (known IDs and names, or a `toolmanifest.vdf` in their folder), and so are games still downloading.
- **Heroic:** the installed-games JSON of each store (`legendaryConfig`, `gog_store`, `nile_config`), titles and art from its library caches, covers Heroic already downloaded to `images-cache/`, playtime from `store/timestamp.json`. DLC is left out.
- **Lutris:** `pga.db` opened read-only; covers from `coverart/` or `banners/`. Games Lutris runs through Steam are left out, since Steam lists them.
- **Your own:** `~/.config/spark-games/games.json`.

A missing launcher isn't an error; its games just don't appear. A file in a format Spark Games doesn't understand is logged and skipped, and the other launchers still show.

## Speed

- The library from the last run (`~/.cache/spark-games/library.json`) shows at once; launchers are scanned again in a background thread.
- Covers are cut once to the tile size with Pillow and cached in `~/.cache/spark-games/covers/`. Only the rows on screen are drawn, so 500 games scroll like 5.
- No polling. When the window gets focus, it compares the modification times of the launchers' files with the last scan and scans again only if something changed.
- When you press Play, a small helper process (`spark-games --track`) starts the game and records the session, so the window can stay open, minimize or close (Settings). For your own games the helper waits for the program to exit. For launcher games it looks every 10 seconds for a process running from the game's folder (it reads `/proc` only).

## Files

Settings in `~/.config/spark-games/` (`config.json`, `games.json`), playtime in `~/.local/share/spark-games/`, cache in `~/.cache/spark-games/`, log in `~/.local/state/spark-games/`. Windows games you add get their own Wine prefix in `~/.local/share/spark-games/prefixes/`.

## Install, run, test

```
sudo bash install.sh --deps                # system-wide with Fedora packages (what the image build runs)
bash install.sh --user                     # for you only, no root: ~/.local/lib/spark-games, ~/.local/bin/spark-games, menu entry, icons
bash install.sh --user --uninstall         # remove exactly what that installed (settings and playtime stay)
python3 spark_games.py                     # run from this folder
python3 spark_games.py --self-test         # parsers against the bundled fixtures, Pillow, xdg-open; no display, no network
SPARK_GAMES_HOME=/some/fake/home python3 spark_games.py    # scan another folder instead of your home (for testing)
python3 -m unittest discover -s tests -v
python3 make_icons.py                      # redraw icons/ after changing the mark
```

On SparkOS, `--user` needs nothing extra: Python 3, Tk and Pillow are in the image. `spark-app.json` describes the app for the future Spark Portal (ID, version, size, what it needs and reads).

The tests use the fixtures in `tests/fixtures/`: a fake home with a Flatpak Steam (two library folders, Proton, a redistributable, a tool found by its `toolmanifest.vdf`, a game still downloading, a hand-written manifest with escaped quotes), a Flatpak Heroic with one game per store and a DLC, and a regular Lutris (`pga.db` is built from `pga.sql`). Covers are drawn by the tests, so no art is copied in. CI ([workflow](../../.github/workflows/spark-games.yml)) runs everything under Xvfb in Fedora. Inside the published SparkOS image it runs the image build step as root followed by `--self-test`, then installs it with `--user` as a normal user, runs `--self-test` and uninstalls it.

## Known gaps

- Not tried with real Steam, Heroic or Lutris libraries yet; only with the fixtures. Heroic's file layout changes between versions, so its covers and playtime are the most likely to need fixing.
- The playtime helper for launcher games finds the game by its install folder on the command line. A game started some other way (a launcher stub elsewhere) may not be counted; the launcher's own playtime is still shown.
- MangoHud and GameMode switches only apply to games you added. For Heroic and Lutris games, use their own per-game settings.
- No Steam non-Steam shortcuts, no itch.io, Bottles or Minecraft launchers yet.
- No gamepad navigation or big-screen mode yet (keyboard only).
- English only for now; every string is in `sparkgames/strings.py`, ready for a French table.
