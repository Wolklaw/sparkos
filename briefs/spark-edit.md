# Spark Edit

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-edit/`, `install.sh` with `--deps` and `--user`, `spark-app.json`,
`--self-test`, tests, workflow, build step `files/scripts/spark-edit.sh`). Don't edit
`recipes/recipe.yml`, `boot-test.yml` or `sparkos-defaults.sh`: the main session wires it in and
makes it the default for text at merge. Say in the PR which MIME types it should own.

## Why

SparkOS has no text editor: Kate and KWrite were removed, so `.txt`, `.md`, `.conf` and code files
open in FreeSuite Writer, an office suite. The owner wants a small, fast Spark tool for this and
as few ties to other projects as possible ([PLAN.md, Independence roadmap](../PLAN.md)).

## What it does

- Opens instantly (under 0.5 s), and opens a 50 MB log file without freezing (load in chunks,
  colour only what's visible).
- Tabs, recent files, reopen last session, an unsaved-changes dot, and autosave of unsaved buffers
  to `~/.local/state/spark-edit/` so a crash or power cut loses nothing.
- Find and replace (case, whole word, regex), go to line, line numbers, word wrap, zoom.
- Syntax colouring for the common types (Python, JS/TS, JSON, YAML, TOML, INI/conf, shell,
  Markdown, HTML/CSS, C/C++, Rust, Go) with small tokenisers in the house palette; no heavy
  dependencies.
- Encodings (detect UTF-8/UTF-16/Latin-1, keep the file's own) and line endings (CRLF files stay
  CRLF), shown in the status bar and changeable.
- Files the user can't write (system files): offer "Save as administrator" through pkexec.
- `spark-edit FILE[:LINE]` from a terminal.

## Done when

CI passes in Fedora and inside `ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`),
the build step exists, the README states the measured open time for a 50 MB file, and a PR from
`spark-edit` is open for the owner.
