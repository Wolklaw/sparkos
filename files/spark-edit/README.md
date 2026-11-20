# Spark Edit

The SparkOS text and code editor: notes, settings files, logs and code. Kate and KWrite are gone from the image, so without it `.txt`, `.md`, `.conf` and code files open in FreeSuite Writer, an office suite. Spark Edit is small (about 600 KB installed, half of it Python's compiled copies; it needs Python and Tk, nothing else) and opens at once.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

It is optional for now: the main SparkOS session decides when it goes into the image ([build step](../scripts/spark-edit.sh)) and makes it the default for text files. It also installs for one user without root (`install.sh --user`), the way optional Spark apps will through the future Spark Portal.

- **Tabs**, one window. `spark-edit FILE` while it is open adds a tab to that window. Ctrl+Tab and Ctrl+PageUp/PageDown switch tabs, Alt+1 to Alt+9 jump to one, Ctrl+W closes, Ctrl+Shift+T reopens the last one closed. A dot on a tab means unsaved changes; undoing back to the saved text clears it.
- **Nothing is lost.** A moment after you stop typing, every unsaved tab is copied to `~/.local/state/spark-edit/autosave/`. Quitting keeps them there: the next start reopens your tabs, unsaved changes included, exactly as you left them (like Notepad on Windows 11). A crash or a power cut leaves the same copies, and they come back the same way. Your file on disk is only written when you save. Turn off "Reopen last session at start" in the menu and quitting asks about each unsaved tab instead.
- **Recent files** on the start screen and in the menu.
- **Find and replace** (Ctrl+F, Ctrl+H): match case, whole word, regular expressions (Python's syntax; `\1` in the replacement), "3 of 12", every match marked on screen, Replace all as one undo step. F3 and Shift+F3 move between matches. **Go to line** (Ctrl+G): `120` or `120:8`.
- **Line numbers, word wrap** (Alt+Z), **zoom** (Ctrl+plus, Ctrl+minus, Ctrl+0, Ctrl+wheel), current line lit.
- **Syntax colours** for Python, JavaScript, TypeScript, JSON, YAML, TOML, INI and conf files (desktop entries, systemd units, KDE's rc files), shell, Markdown, HTML and XML, CSS, C, C++, Rust and Go, from small tokenisers in [`syntax.py`](sparkedit/syntax.py) in the house palette. The language is picked from the file name or the `#!` line; click it in the status bar to change it.
- **Files stay as they were.** The encoding (UTF-8, UTF-8 with BOM, UTF-16 LE/BE, Latin-1, Windows-1252) and the line endings (LF, CRLF, CR) are detected and kept: a CRLF file stays CRLF. Both are shown in the status bar; click them to reopen with another encoding or to save with another encoding or line ending. A character the file's encoding can't hold is pointed out, with an offer to save as UTF-8. Binary files are recognised and not opened unless you say so.
- **Save as administrator.** Saving a file you can't write (most of `/etc`) offers "Save as administrator": pkexec asks for your password in Plasma's own prompt and copies the new text over the file, keeping its owner and permissions. Files under `/usr` are on SparkOS's read-only image; Spark Edit says so instead of asking for a password that can't help.
- **Changed elsewhere?** A file another program changed is reloaded when you come back to the window (unless you have unsaved edits in it; then saving asks before overwriting).
- Small editing helpers: Enter keeps the indentation (and adds a level after `:` in Python or `{` in C-like languages), Tab and Shift+Tab indent and unindent selected lines, Backspace in the indentation goes back one level, Home goes to the first character of the line, Ctrl+/ comments or uncomments lines. Indenting with tabs or spaces follows what the file already does.
- `spark-edit FILE`, `spark-edit FILE:LINE` and `spark-edit FILE:LINE:COLUMN`, the way compilers and `grep -n` print places. A file that doesn't exist yet opens empty and is created when you save.

## How it works

- **Big files.** The file is read and decoded in a worker thread, the first 96 KB go into the editor at once, and the rest is added in slices of about 25 ms, so the window keeps answering while a big file loads. Files over 5 MB open without word wrap, which Tk is slow at for very long files.
- **Changes to the text, not to the view, redo the work.** Refreshing the colours of the visible lines re-tags them, and Tk then measures them again and reports a scroll; the refresh only touches the text when the visible lines, the text or the language changed, so an idle window does nothing.
- **Colour only what's visible.** After each scroll or edit, the lines on screen plus 40 above and below are coloured; nothing else is. For languages where a comment or string can run over many lines, the state at the start of each line is remembered from the top down to where you have looked, and forgotten from an edited line on. Jump to the middle of a big file and the lines on screen are coloured right away, while the real state at that point is worked out in the background a few thousand lines at a time; lines longer than 5,000 characters are coloured up to there.
- **Change tracking.** A small proxy sits in front of the Text widget's Tcl command (the way IDLE does it), so every insert and delete says which line changed. Line numbers are drawn for the visible lines only.
- **Saving** writes a temporary file next to the original, flushes it to disk, and swaps it in, so a crash in the middle of a save never leaves half a file. Permissions and group are kept, symlinks stay links (the file they point to is saved), and files with hard links are written in place so the links stay.
- **One window.** A Unix socket in `$XDG_RUNTIME_DIR` hands `spark-edit FILE` to the open window before Tk is even loaded. `--new-window` starts a separate one.
- File dialogs are Plasma's own (kdialog), run in a worker thread so the window keeps drawing; Tk's own dialogs are used where kdialog isn't installed.

Settings are in `~/.config/spark-edit/`, the session, the autosaves and the log in `~/.local/state/spark-edit/`.

## Speed

Targets from the brief: open in under 0.5 s, and open a 50 MB log file without freezing.

Measured by CI on 2026-11-20 (GitHub runner: 4 vCPUs of an AMD EPYC 7763, Fedora, Python 3.15.2, Tk 9.0 — the same Python and Tk as the SparkOS image — under Xvfb), three runs each, times from the moment the process started:

| | Window shown | First screen of the file | Whole file in, editable | Longest the window didn't answer | Memory |
|---|---|---|---|---|---|
| Start, no file | 0.17–0.19 s | | | | 39 MB |
| **50 MB log file** (470,394 lines) | 0.18–0.32 s | 0.33–0.38 s | **0.45–0.53 s** | 32–120 ms | 321 MB |

Both targets are met: the window is up in under 0.2 s, and a 50 MB log is on screen in under 0.4 s and fully editable in about half a second, with the window answering at least every 0.12 s while it loads. Once it is in, jumping to the end takes 5–7 ms. Reading the whole 50 MB back out of the editor, which Find (in files that big) and Save start with, takes about 0.2 s. On the development PC under Windows 11 (Python 3.13, Tk 8.6) the same file was editable after 0.72 s. It hasn't been measured on a SparkOS desktop yet (the SparkOS image has no Xvfb, so CI can't open a window inside it); run the line below there.

`spark-edit --bench FILE` measures the same on any PC: it opens the window and the file, and reports when the window was shown, when the first screen of the file was drawn, when the whole file was in the editor and editable (all counted from the moment the process started, Python's own start-up included), the longest the window went without answering while loading, and how long jumping to the end takes. `tests/make_log.py big.log 50` writes the test file.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
spark-edit notes.txt                      # or from the app menu, or "Open with" in Dolphin
spark-edit src/main.c:120:8               # open at line 120, column 8
spark-edit --self-test                    # what it needs, checked without a display
spark-edit --bench big.log                # open time for a file
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark
```

`--user` needs only what the SparkOS image already has (Python 3 with tkinter). It installs to `~/.local/lib/spark-edit/`, `~/.local/bin/spark-edit`, `~/.local/share/applications/` and `~/.local/share/icons/`, and lists every file it wrote in `~/.local/lib/spark-edit/installed-files` for `--uninstall`. Settings, the session and unsaved work are left in place by `--uninstall`.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, what it needs, how to install it).

The tests cover reading and writing every encoding and line ending byte for byte, binary files, permissions, symlinks and hard links, Save as administrator through a stand-in pkexec, every tokeniser, find and replace, the autosave and crash recovery, and the window itself (typing, undo back to clean, indenting, find and replace all, loading a 10 MB file in slices, colouring far down a file, handing a file to the open window). CI ([workflow](../../.github/workflows/spark-edit.yml)) runs the image build step and all of them under Xvfb as a normal user in Fedora, measures the speed, and inside the published SparkOS image installs it with `--user` as a normal user, runs the self-test and the tests on the image's own Python 3.15 and Tk 9.0, and uninstalls it, checking nothing is left in `~/.local` or `/usr`. The image has no Xvfb, so the window tests and the speed measurement run in the Fedora job only (same Python and Tk).

## Known gaps

- **Not tried on a SparkOS desktop yet.** The interface was checked on Windows and runs under Xvfb in CI; nobody has used it on real Plasma 6.8 yet, so the kdialog file dialogs and the pkexec password prompt haven't been seen there.
- **Syntax colours are simple.** Each language is a small tokeniser, not a parser: the contents of `<script>` and `<style>` in HTML aren't coloured, nor are shell here-documents, nested Rust block comments or JavaScript regular expressions.
- **Very long lines are shown cut at the window's edge.** Tk's text widget takes seconds to minutes to scroll sideways along, wrap, or follow the cursor on a single line of hundreds of thousands of characters (minified JavaScript, one-line JSON). In a file with a line over 20,000 characters, Spark Edit turns word wrap off and doesn't scroll sideways, and the status bar says so: the file opens at once (a 656 KB one-line JSON file in 0.5 s) and stays responsive, Find, Replace and Save work on all of it, but the end of such a line can't be seen.
- Find counts and Replace all work on the whole text in memory; on a 50 MB file a search over everything takes a few tenths of a second, and in files over 4 MB Find waits for Enter instead of searching as you type.
- No spell check, no split view, no printing.
- The clipboard follows X11 rules (Tk runs under XWayland): text you copied is gone when Spark Edit quits unless Plasma's clipboard keeps it (it does by default).
- English only for now; every sentence is in [`text.py`](sparkedit/text.py), ready for a French table.
