# Spark Run

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-run/`, `install.sh`, `spark-app.json`, `--self-test`, tests, workflow, build
step `files/scripts/spark-run.sh`). Don't edit `recipes/recipe.yml`, `boot-test.yml`,
`sparkos-defaults.sh` or `files/system/usr/bin/sparkos-open-package`; say in the PR how the main
session should hook it into double-clicking an `.exe` or `.msi`.

## Why

Double-clicking a Windows `.exe` on SparkOS fetches Bottles (another project's app) from Flathub
and opens the file there. The owner wants as few ties to other projects as possible
([PLAN.md, Independence roadmap](../PLAN.md)). Spark Run is SparkOS's own way to run Windows
programs, still on Wine underneath (Wine is kept on purpose).

## Decide first, then build

Find out which Wine is available and what each choice costs, pick one and explain it in the PR:
- Wine from Fedora in the image (the `wine` package): measure the image size it adds.
- A Wine or Proton build downloaded on first use into `~/.local/share/spark-run/` (which build,
  from whom, verified how).
- What Bazzite already ships that can run `.exe` files (check with the `inspect` workflow).

The owner wants SparkOS light: don't add more than about 300 MB to the image without saying so
plainly in the PR.

## What it does

- Double-click an `.exe` or `.msi`: "Run once" or "Install as an app". Installing makes a separate
  Wine prefix per app under `~/.local/share/spark-run/prefixes/<name>`, runs the installer, finds
  the installed program and adds a menu entry with its icon (read from the `.exe`'s resources).
- A small window listing installed Windows apps: open, open its `C:` folder, uninstall (delete the
  prefix and menu entry), and per-app options (Windows version, DXVK on or off if available).
- Plain errors when a program can't run, with a link to the switching guide, never a stack trace.

## Done when

CI passes in Fedora and inside `ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`),
running a tiny test `.exe` built in CI (for example a hello-world cross-compiled with mingw) and a
tiny test installer, the build step exists, and a PR from `spark-run` is open for the owner with
the Wine choice explained.
