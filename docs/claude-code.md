# Claude Code on SparkOS

SparkOS is set up so Claude Code is a click away. Claude Code itself comes from Anthropic's official installer and updates itself. SparkOS adds the launchers, the sandbox tools and an importer for your Windows setup.

## First time (about two minutes)

1. Open **Claude Code** from the app menu (Development). The first time, it installs Claude Code into `~/.local` with Anthropic's installer. No admin password is needed.
2. Pick a project folder. Claude Code starts there and asks you to sign in through the browser.
3. Bring over your Windows setup. Your Windows drives are already open at `/var/mnt/<letter>` ([windows-drives.md](windows-drives.md)). **With Nova installed** (`bash "/var/mnt/e/Personal Projects/JARVIS/linux/install.sh" --user`), nothing else is needed: each time Claude Code starts, your Windows setup is shared live, not copied (global `CLAUDE.md`, skills, settings, and every project's memory and session history). Without Nova, copy the basics once with:
   ```bash
   sparkos-claude-import
   ```
   This copies `CLAUDE.md`, `skills/` (your house-style skill included), `agents/`, `commands/` and `output-styles/` into `~/.claude`. It never overwrites a file SparkOS already has. It also lists any files that mention Windows paths like `E:\Personal Projects`, so you can change them to where those folders are on SparkOS. Your Windows `settings.json` is saved as `settings.windows.json` for reference only, because its permissions and shell commands are written for Windows.

## Every day

| To | Do |
|---|---|
| Open Claude Code in a project | Right-click the folder in Spark Files and choose **Open Claude Code here** |
| Pick a folder (starts at the last one) | App menu: **Claude Code** |
| From a terminal | `sparkos-claude` (current folder or a picker) or `sparkos-claude ~/path/to/project` |
| Update | Nothing to do: Claude Code updates itself |
| Reinstall or repair | `sparkos-dev-setup --claude` |

## What SparkOS provides

- **Sandbox tools:** `bubblewrap` and `socat` are in the image, so Claude Code's command sandbox works without installing anything. Check it with `/sandbox` inside Claude Code.
- **Developer tools:** `git` is built in. `sparkos-dev-setup` adds Node, Python 3.13, GitHub CLI and JDK 17 with Homebrew, which covers the tools your projects use.
- **The default browser** for sign-in links is Soot.
- **A boot-test check on every build:** the image is booted in a VM, Claude Code is installed with `sparkos-dev-setup --claude`, and `claude --version` has to run.

## Limits, from Anthropic's docs (checked 2026-11-19)

- Anthropic's docs list Ubuntu, Debian and Alpine for Claude Code. Fedora-based systems like SparkOS aren't named. They aren't excluded either, and the SparkOS boot test installs and runs Claude Code on every build.
- The **Claude desktop app** (Chat, Cowork, Code tab) has a Linux beta for Ubuntu and Debian only. Its docs say to use the CLI on Fedora. Use claude.ai in the browser for chat.
- Your project memories and session history from Windows (`~/.claude/projects/...`) are filed under Windows folder paths. Nova links each one to the same project's SparkOS path (`E:\Personal Projects\X` is `/var/mnt/e/Personal Projects/X`), so they load on SparkOS and `claude --resume` lists the Windows sessions. `sparkos-claude-import` alone doesn't do this. Project `CLAUDE.md` files inside your repos come along with the repos.
