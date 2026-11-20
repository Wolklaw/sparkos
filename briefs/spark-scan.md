# Spark Scan

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-scan/`, `install.sh` with `--deps` and `--user`, `spark-app.json`,
`--self-test`, tests, workflow, build step `files/scripts/spark-scan.sh`). Don't edit
`recipes/recipe.yml` or `boot-test.yml`; the main session wires it in at merge.

## Why

SparkOS has scanner support (SANE with the `pixma` and `airscan` backends, for the owner's Canon
TR4700) but no scanning app: the switching guide sends people to Skanpage, another project's app.
The owner wants a small Spark tool instead ([PLAN.md](../PLAN.md)).

## What it does

- Finds scanners (`scanimage -L`, or python-sane if it's in the image; check), remembers the last
  one, and says plainly when none is found, with what to check (power, USB or Wi-Fi).
- Preview scan, drag to crop, then scan at 150/300/600 dpi in colour, grey or black and white.
- Multi-page: scan pages one after another, reorder and delete them, then save one PDF, or PNG/JPG
  per page.
- Optional OCR: make the PDF searchable with tesseract (already in the image for Spark Snip).
- Saves to `Scans` in the user's Documents folder (`xdg-user-dir DOCUMENTS`), named by date.
- Scanning runs in the background with progress and Cancel.

## Testing without a scanner

SANE ships a `test` backend (`scanimage -d test`); use it in CI for the full scan, crop,
multi-page and PDF path. Real Canon scanning is checked by the owner on hardware (Phase 5).

## Done when

CI passes in Fedora and inside `ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`)
using SANE's test device, the build step exists, `docs/switching.md`'s Canon scanner line points to
Spark Scan, and a PR from `spark-scan` is open for the owner.
