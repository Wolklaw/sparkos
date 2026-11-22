# Spark Store

SparkOS's own app store. It lists the Spark apps first, then every app on Flathub, and installs them for you with one click. It is the store on SparkOS (it replaced Bazaar) and the "Spark Portal" for optional Spark apps.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

It is the default store: the taskbar pins it, and `.flatpakref` and `.flatpakrepo` files and `appstream://` links open in it. On the Bazzite base, Bazaar stays installed for now and is only used where Spark Store is missing; the Fedora base has no Bazaar. The image build step is [files/scripts/spark-store.sh](../scripts/spark-store.sh). It also installs for one user without root (`install.sh --user`).

## What it does

- **Home:** the Spark apps (read from each app's `spark-app.json`; installed ones marked, optional ones installable), then rows of well-known apps: Games, Chat, Music, Creative, Office. Each row is a short list of known apps ([sparkstore/catalog.py](sparkstore/catalog.py)), filled from the matching Flathub categories when some are missing. At the bottom, **Browse** opens every app in a category (Games, Music & video, Graphics & photos, Internet & chat, Office, Development, Education & science, Utilities, System), verified apps first, 60 at a time.
- **Search as you type,** across names, keywords, summaries and who makes the app. Every word has to match somewhere; a match in the name counts most. Accents don't matter ("edition" finds "Édition"). Enter opens the first result.
- **App pages:** icon, name, who makes it ("Verified" when Flathub has confirmed the developer, and a note when it hasn't), summary, screenshots, description, size, licence, version, and **what it can use**, in plain words, grouped as files, devices, network and other. Lines that reach outside the sandbox (every file in your home folder, all devices, the X11 display, your saved passwords...) are marked. Proprietary apps say so at the top, in a box of their own: the code isn't public, so only the maker can check what it does.
- **Add-ons** (Flatpak extensions: OBS plugins, Steam's compatibility tools, GIMP plugins...) are listed on their app's page and install or remove for you through the same queue, once the app is installed.
- **Install / Open / Remove.** Installs use `flatpak install --user`: no password, only for you. Removing asks first, keeps the app's settings in `~/.var/app/<id>` unless you pick "Remove with its data", and warns when an app is installed for everyone (then SparkOS may ask for a password).
- **One queue.** Installs, updates and removals run one at a time in a background thread. A bar at the bottom shows what's running and its progress; the Queue page lists everything, lets you cancel, and shows flatpak's own error with **Retry** when something fails. Closing the window while something installs hides it until the queue is done.
- **Installed** lists the Spark apps and the Flatpak apps (for you, or for everyone) with their size, and can remove runtimes no app uses any more (`flatpak uninstall --user --unused`). **Updates** lists apps with an update, with **Update all**; it checks Flathub when you ask, and by itself at most every 6 hours.
- **Links:** opening a `.flatpakref` file or an `appstream://` link (or `spark-store <app id>`) lands on that app's page. A `.flatpakref` from somewhere other than Flathub gets its own page that names the source and says SparkOS doesn't check it. A `.flatpakrepo` file (a whole app source) gets a page that names it and its address, says SparkOS doesn't check it, and adds it for you only (`flatpak remote-add --user --from`); its apps are then installed from that source's own links, since the Store's catalog lists Flathub only. If the Store is already open, the open window takes the link.

## Where the data comes from

- **The catalog** is the Flathub catalog flatpak keeps on the PC: `<installation>/appstream/flathub/<arch>/active/appstream.xml.gz` and its `icons/`, for you (`~/.local/share/flatpak`) and for everyone (`/var/lib/flatpak`); the newer one wins. SparkOS fetches it at first boot. The Store reads it once into a small index (`~/.cache/spark-store/catalog.sqlite`) and reads it again only when flatpak replaces the file, so search works offline and the window opens at once. If the catalog is more than a day old, the Store asks your own flatpak for a newer one in the background (`flatpak update --user --appstream flathub`); if it's missing, Home says so and offers to get it.
- **Size and permissions** come from `flatpak remote-info`, which reads Flathub's index that flatpak keeps; installed apps use `flatpak info --show-metadata`. Sizes are in Windows units (1 KB = 1024 bytes), so they read a little smaller than flatpak's.
- **Screenshots** are downloaded only when an app's page opens, from the HTTPS address in the catalog, and kept in `~/.cache/spark-store/shots` (at most 400 files).
- **No web API, no account, no tracking.** Nothing is sent anywhere except flatpak's own requests to Flathub and plain downloads of screenshots.

## Spark apps

The Store finds Spark apps by their `spark-app.json`:

1. in its own `spark-apps/` folder: `install.sh` copies every sibling `files/spark-*/spark-app.json` and its icon there (the image build does the same);
2. in the installed apps: `/usr/lib/<slug>/` (in the image) and `~/.local/lib/<slug>/` (per user).

The apps that don't have a `spark-app.json` yet (Soot and FreeSuite, which come from their own repositories, and Spark Snip and Spark Media) are described in [sparkstore/own-apps.json](sparkstore/own-apps.json). The Spark apps don't all use the same keys yet (`summary` or `description`, `size_kb` or `installed_size_kb`); the reader takes both.

An app is "installed" when its desktop entry is there, "for you" when it is in `~/.local`. An optional Spark app can be installed only when its source folder (with `install.sh` and `spark-app.json`) is on the PC, in `~/.local/share/spark-store/sources/<slug>` or `/usr/share/spark-store/sources/<slug>`: the Store then runs `install.sh --user` through the queue. **How optional Spark apps will be downloaded isn't decided** (release tarballs checked against SHA256SUMS, or the owner's own Flatpak repository), so the Store downloads none and says so on the app's page. Today every Spark app ships in the image, so this doesn't come up yet.

## Speed

Targets from the brief: open in under a second with thousands of apps, and no CPU when idle.

Measured by CI on 2026-11-20 (GitHub runner: 4 vCPUs of an Intel Xeon 6975P-C, Fedora, Xvfb) with the real Flathub catalog of 3,366 apps, `spark-store --bench 10`:

| Run | First paint | All 3,366 apps on screen | Idle CPU (one core = 100%) |
|---|---|---|---|
| First ever (index built) | 0.30 s | 1.30 s (index: 1.15 s) | 0.20% |
| Every run after | 0.22 s | 0.21 s (index: 0.05 s) | 0.20% |
| Animations off | 0.22 s | 0.21 s | 0.00% |

First paint counts from the moment the process started, Python's own start-up included. A search over all apps takes about 8 ms. It hasn't been measured on the owner's Ryzen yet; `spark-store --bench 10` measures it on any PC.

- The window, the Spark apps and the header are drawn first; the catalog index, the installed list and the update check load in threads. Icons load a few per idle moment.
- When nothing is running, nothing is scheduled: the window only polls while a background job or the queue is busy. The idle 0.2% is the glitch on the title (every 7-12 s); it's off when Plasma's animations are off, and then the Store uses no CPU.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (what the image build runs)
spark-store                               # open
spark-store appstream://org.gimp.GIMP     # open on an app's page (also: an app ID, a .flatpakref file)
spark-store --page updates                # open on Installed, Updates or Queue
spark-store --self-test                   # what it needs and finds; reads the catalog; no display needed
spark-store --bench 10                    # time to first paint and to the catalog, idle CPU
python -m unittest discover -s tests -v   # tests (UI tests need a display: xvfb-run on CI)
python make_icons.py                      # redraw icons/ from code
```

The tests use [tests/fake_flatpak.py](tests/fake_flatpak.py) in place of flatpak, and [tests/fixtures/appstream.xml](tests/fixtures/appstream.xml), a small catalog with invented apps. CI ([.github/workflows/spark-store.yml](../../.github/workflows/spark-store.yml)) also runs the build step in Fedora, downloads the real Flathub catalog through flatpak and self-tests against it, and inside the SparkOS image installs it for a normal user, tests, and removes it. No real app is installed in CI.

Settings are in `~/.config/spark-store/`, the log in `~/.local/state/spark-store/`, the index and screenshots in `~/.cache/spark-store/`. The interface is in English and French (from `LANG`); every sentence is in [sparkstore/text.py](sparkstore/text.py).

Keys: Ctrl+F search, Enter open the first result, Esc clear the search or go back, Alt+Left back, Ctrl+1-4 pages, F5 refresh, Ctrl+Q close.

## Not done yet

- Opened on a real SparkOS desktop in CI, not used by hand yet. The boot test opens it from the app menu in a Plasma 6.8 session in a VM, in English and in French, keeps a screenshot and fails on a Python traceback. CI also covers the window under Xvfb (with a fake flatpak for most tests, and one real Flathub app installed and removed through the window), and the real queue inside the SparkOS image.
- Apps from sources other than Flathub aren't in the catalog: they install from their own `.flatpakref` links.
- Installs are always for you only; apps installed for everyone can be updated and removed (with a password), not installed.
- No ratings or download counts: those need Flathub's web API, which the brief rules out.
- No update notifications: the Store shows updates while it's open.
