# Contributing to SparkOS

SparkOS is my project: I decide what goes in and how it works. But anyone can propose a change.
If I merge it, it ships in the next daily image to every SparkOS PC, with your name in the commit.

## Ways to help

- **Hardware reports.** Only one PC has run SparkOS so far (Ryzen 7 7800X3D, Radeon RX 6800 XT).
  If you install it, open an [issue](https://github.com/Wolklaw/sparkos/issues) with your CPU,
  graphics card and what worked or didn't. Nvidia and Secure Boot reports are the most wanted.
- **Bug reports.** What you did, what happened, what you expected. `journalctl -b` output or a
  screenshot helps.
- **Pull requests.** Fixes, new features in a Spark app, a new Spark app, translations (every app
  has French next to English), drivers for hardware SparkOS doesn't handle yet.

For something big (a new app, a change to the desktop, a new package in the image), open an issue
first and ask. I'd rather say no before you spend a weekend on it than after.

## What I'll merge

- It fits SparkOS: a gaming and everyday desktop for people coming from Windows.
- It's SparkOS's own code, or a small, well-known dependency. I want fewer third-party parts, not
  more, so a pull request that adds a package to the image needs a good reason.
- It doesn't bring KDE, Plasma or KWin back: the build fails if a KDE package gets in.
- Copy is plain: plain verbs, honest about what works and what's untested.
- It comes with tests where the code has them, and the docs say what changed.

## Making a change

1. Fork the repository and make a branch.
2. Change the code. The layout:
   - `files/spark-*`: each Spark app or desktop part, with its own README, `tests/` and
     `spark-app.json` (bump `version` there when you change an app).
   - `files/spark-compositor`, `files/spark-shell`: the desktop itself.
   - `build_files/` and `Containerfile`: how the image is built ([docs/building.md](docs/building.md)).
   - `files/scripts/`: build-time scripts, run in order.
   - `docs/`: how things work and why.
3. Test it:
   - An app: its workflow, `.github/workflows/spark-<app>.yml`, shows exactly what CI runs:
     usually the app's `--self-test`, then its tests under Xvfb
     (`xvfb-run -a python3 -m unittest discover -s tests`, in English and in French). The same
     checks run on your pull request, so you can also let CI do it.
   - The image: `sudo podman build -t localhost/sparkos:test .` (about 40 GB free), then try it in
     a VM ([docs/vm-test.md](docs/vm-test.md)). Don't test desktop changes on a PC you depend on.
4. Open a pull request against `main` and fill in the template.

## What happens next

- Your first pull request waits for me to approve its CI run (GitHub's rule for new
  contributors). After that, CI builds the image and runs the app's checks on every push.
- Pull request builds aren't signed or published; only `main` is. Nothing you push reaches anyone's
  PC until I merge it.
- I review it, may ask for changes, or may change it myself before merging. I may also say no.
- Merged changes go out in the next daily image (06:00 UTC); Spark apps with live updates can go
  out sooner.

## License

SparkOS is source-available, not open source ([LICENSE](LICENSE)). The license lets you fork and
change it to propose a pull request here. By sending a contribution you give me the rights to use
it in SparkOS, as LICENSE describes; you keep your copyright. If your change contains anyone
else's code, artwork or sound, name it and its license in the pull request.
