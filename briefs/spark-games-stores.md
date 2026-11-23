# Spark Games: stores and launchers without Heroic or Lutris

Read [README.md](README.md) first, then [files/spark-games/README.md](../files/spark-games/README.md).
This extends Spark Games; it is not a new app. Work on a branch `spark-games-stores`, keep every
existing source working, and open a PR for the owner.

## Why

Spark Games 1.0 lists Epic, GOG and Amazon games by reading Heroic's files, and Battle.net, EA and
Ubisoft games by reading Lutris's database. It also starts them through `heroic://` and `lutris:`, so
both apps still have to be installed. The owner wants as little software from others as possible
([PLAN.md](../PLAN.md), "Independence roadmap"; owner's decision 2026-11-22). Spark Games should sign
in to these stores, install their games and start them by itself, with Heroic and Lutris no longer needed.

The engines underneath stay other people's work, like Wine and Proton: the store clients that Heroic
itself runs (**legendary** for Epic, **gogdl** for GOG, **nile** for Amazon, all GPL-3.0) and
**umu-run** with Proton (already in the image, `build_files/packages.sh`). Spark Games runs them as
separate programs and never imports their code, so its own licence doesn't change. List them in
[THIRD-PARTY.md](../THIRD-PARTY.md).

## Decide first, then build

Explain each choice in the PR:
- **Where the three clients come from.** Check Fedora's and Terra's packages first, then each
  project's own releases (Heroic keeps maintained forks of legendary and gogdl; upstream legendary
  has been slow). Use a build that is maintained today. Either ship pinned versions in the image
  under `/usr/lib/spark-games/runners/` with SHA-256 checks in the build step, or download them on
  first use into `~/.local/share/spark-games/runners/`, checked the same way (Spark Run's Wine
  download is the pattern). Say what each adds to the image.
- **How sign-in works in a Tk app.** Epic and GOG finish sign-in by redirecting to a page whose URL
  or body holds an authorization code (legendary: `auth --code`; gogdl: the `code` from
  `embed.gog.com/on_login_success`); Amazon's nile has its own flow. Best: a small sign-in window
  that catches the code by itself (WebKitGTK through PyGObject, or Qt WebEngine, whichever the
  image already has; check before adding anything). Fallback that must always work: open the
  store's page in the default browser (Soot) and paste the code into Spark Games. Tokens go in
  `~/.config/spark-games/accounts/`, mode 0600, and are never logged.
- **Proton.** Which Proton umu-run uses by default (UMU-Proton, downloaded by umu) and whether
  Spark Games offers a choice per game.

## What it does

**Accounts.** Settings > Accounts: Epic Games, GOG, Amazon Games. Sign in, see who's signed in,
sign out (deletes the tokens). Each one says plainly that it's that company's account and store.

**Owned games, not only installed ones.** A game you own but haven't installed shows in the library
greyed out, with Install. The store filter gets "Installed" and "All owned". The owned list is
fetched in the background at most once a day, or when asked (F5), and cached.

**Install, update, uninstall.** Pick the folder (default `~/Games/<store>/`; offer the games drive
if one is set), see the download size and the free space before starting, then a progress bar with
speed and time left that keeps going if the window closes (a helper process, like `--track`). Pause,
resume, cancel. Updates: the game page says when one is waiting and Play offers "Update first" or
"Play anyway". Verify/repair. Uninstall asks once and says how much space it frees. Cloud saves
sync on start and exit where the client supports it (legendary `sync-saves`, gogdl's save sync),
with a switch per game.

**Play.** Spark Games starts the game itself: the client's launch command (legendary `launch
--dry-run` gives the command, or the client's own launch through umu-run), with MangoHud and
GameMode switches working for these games too (today they only work for games you added). Epic's
online games get their launch token from legendary at each start. A plain error when the game
can't start, never a stack trace.

**Battle.net, EA app, Ubisoft Connect (what Lutris did).** "Add a launcher": Spark Games downloads
the official installer from the company's own site, makes a prefix for it under
`~/.local/share/spark-games/prefixes/<launcher>`, runs the installer through umu-run with the game
ID umu-protonfixes uses for it (so known fixes apply), and adds the launcher to the library. v1: the
launcher is one tile that opens it; games inside it are a later step (reading Battle.net's
`product.db` or the prefix's registry). Rockstar Games Launcher and the itch app the same way if
it's cheap.

**Taking over what's already installed.** The owner has games installed through Heroic and Lutris
on this PC. Spark Games must take them over without downloading them again: import Heroic's
installed Epic/GOG/Amazon games into the clients' own records (legendary `import`, gogdl and nile
equivalents, or reading Heroic's `installed.json`), and pick up Lutris's Wine prefixes for
Battle.net/EA/Ubisoft. Ask once ("Use the games Heroic installed? They won't be downloaded again"),
then those games start through Spark Games. Never delete or change Heroic's or Lutris's files.
Keep reading Heroic and Lutris as sources for anyone who keeps using them, but the same game must
never show twice.

**Store.** When this works, Spark Store stops suggesting Heroic and Lutris on the games page
(`files/spark-store/sparkstore/catalog.py`); they stay installable by search. Don't change the
catalog in this PR; say in the PR that it's ready for the main session to do.

## Both bases

It must work natively on both images, `ghcr.io/wolklaw/sparkos` (Bazzite) and
`ghcr.io/wolklaw/sparkos-fedora` (plain Fedora; [docs/fedora-base.md](../docs/fedora-base.md)).
`umu-run` is in both. WebKit isn't pulled in on the Fedora base, so check each image before picking
the sign-in window; the paste fallback must work on both. CI runs the in-image job in both.

## Speed and safety

- Opening the app stays under a second: accounts and owned lists come from cache, refreshed in the
  background. Nothing polls while idle.
- Downloads never block the window. Only one install at a time per disk; the rest queue.
- No account data leaves the PC except to the store it belongs to. Nothing goes to SparkOS.

## Tests

- Unit tests with recorded client output (fake `legendary`, `gogdl`, `nile` scripts in
  `tests/fixtures/` that print saved JSON), no network and no real accounts in CI: owned lists,
  install progress parsing, update detection, launch command, import from the Heroic fixture
  already there, the same game never listed twice.
- The sign-in paste flow under Xvfb.
- `--self-test` reports which clients are present and their versions.
- The owner tries the real thing on their PC: sign in to Epic and GOG, install a small free game,
  play it, take over one game Heroic had installed. Mark each one done or not in the README's
  "Known gaps".

## Done when

CI passes (Fedora and inside `ghcr.io/wolklaw/sparkos:latest`), the README's tables say how each
store and launcher works now, French strings are in `strings.py`, and the PR is open with the
three decisions above explained.
