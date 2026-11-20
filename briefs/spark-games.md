# Spark Games

Read [README.md](README.md) first for the conventions every Spark app follows.

**The owner had already started writing this app's idea before this brief existed. Ask them for their
notes first and treat theirs as the source of truth where they differ from this brief.**

## Why

SparkOS is a gaming OS that ships no game launcher. Users will install Steam, Heroic, Lutris and
others, and end up with games spread across several apps. Spark Games is SparkOS's front door to
playing: one library of every installed game, whatever launcher it came from, in the house style.

It is a library and launcher, not a store. Buying, downloading, updates, cloud saves and friends stay
in each launcher. Spark Games starts games through them, so nothing breaks in Steam or Heroic.

## What it does

**Library.** A grid of covers (and a compact list view) of every installed game, sorted by recently
played, with search as you type and filters by launcher. Each tile shows the cover, title, launcher
badge and playtime. Opens straight to the library; the app starts in under a second even with
hundreds of games (scan in the background, show the cached library first).

**Sources.** Read each launcher's own files; never change them. Check both the regular and the
Flatpak locations (on SparkOS these launchers are Flatpaks, under `~/.var/app/<id>/`):

- **Steam** (`com.valvesoftware.Steam`, or `~/.local/share/Steam`): `steamapps/libraryfolders.vdf`
  for library folders, `appmanifest_<appid>.acf` for installed games (skip Proton, runtimes and
  redistributables: tools have no `LastPlayed` or are in Steam's tool list). Covers from
  `appcache/librarycache/<appid>/`. Playtime and last played from
  `userdata/<id>/config/localconfig.vdf`. Launch with `steam steam://rungameid/<appid>` (or the
  Flatpak's `flatpak run com.valvesoftware.Steam steam://rungameid/<appid>`).
- **Heroic** (Epic, GOG, Amazon; `com.heroicgameslauncher.hgl`): its config folder holds the
  installed-games JSON per store (`legendaryConfig`, `gog_store`, `nile_config`) and cached images.
  Launch with `heroic://launch/<runner>/<appName>` through `xdg-open`.
- **Lutris** (Battle.net and others; `net.lutris.Lutris`): `pga.db` (SQLite) for installed games,
  covers from its `coverart`/`banners` folders. Launch with `lutris:rungameid/<id>`.
- **Your own games:** "Add a game" picks a native program or a Windows `.exe`. Windows games run
  with `umu-run` (umu-launcher) and Proton if available; otherwise offer Bottles. Store these in
  `~/.config/spark-games/games.json`.

A missing launcher is not an error; its section just doesn't appear. A launcher whose files changed
format logs a warning and is skipped, never crashes the app.

**Game page.** Big cover, title, launcher, playtime, last played, install folder (opens in Dolphin),
and Play. Per-game options Spark Games can apply itself when it starts the game:

- FPS and performance overlay (MangoHud, already in Bazzite: `MANGOHUD=1`).
- GameMode (`gamemoderun`, also in Bazzite).
- For Steam games, these go through Steam's launch options, which Spark Games must not edit while
  Steam runs. Show the line to paste (`MANGOHUD=1 gamemoderun %command%`) with a Copy button instead.

**Playtime.** Show each launcher's own playtime. For games started from Spark Games, also record
sessions in `~/.local/share/spark-games/playtime.json` (start, end, game), so non-Steam games get
playtime too.

**Anti-cheat warning (optional, online).** Games with kernel anti-cheat don't run on Linux. If online,
fetch the public AreWeAntiCheatYet game list (cache it for a week in `~/.cache/spark-games/`) and mark
games listed as denied or broken. Offline, show nothing. Say where the data comes from.

**Empty state.** No launcher installed: say so and offer to open Spark Welcome's Games page (if
installed) or the Store.

**Controllers.** Keyboard first: arrows, Enter to play, `/` to search, Esc back. Gamepad navigation
(SDL2 or `python3-evdev`) is a good second step, for a couch "big screen" mode; not needed for v1.

## Speed

- Parse launcher files in a background thread; cache the library in
  `~/.cache/spark-games/library.json` and show it at once on the next start.
- Thumbnail covers once with Pillow into the cache at the tile size. Never load full-size art for the
  grid.
- Zero CPU when idle. Don't poll launchers; rescan on window focus if their files changed (mtime).
- While a game runs, Spark Games uses nothing: minimize to the tray or close, as the user chooses.

## Tests

- Unit: parsers for each source against fixture files in `tests/fixtures/` (a Steam library with two
  library folders and a tool to skip, Heroic JSON for each store, a small Lutris `pga.db`), the VDF
  parser (text VDF, nested, escaped quotes), launch commands for regular and Flatpak installs,
  playtime recording.
- UI under Xvfb: the grid renders 500 fake games and scrolls; search filters; the empty state shows.
- `--self-test`: parsers load the bundled fixtures, Pillow works, `xdg-open` exists. No network.
- Boot test: run `--self-test` in the real image.

## Done when

The image builds with Spark Games, CI and the boot test pass, the app finds games from Steam and
Heroic test fixtures, and the PR is open for the owner. The owner will test it on real hardware
with their real libraries in Phase 5.
