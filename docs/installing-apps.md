# Installing apps on SparkOS (for Windows users)

On SparkOS, installing apps works the way you're used to: a store with an Install button, or a downloaded file you double-click. No terminal needed.

## The usual way: the Store

Open **Bazaar** from the app menu or the taskbar. It's SparkOS's app store, like the Microsoft Store.

- Search for the app and press **Install**. No restart is needed.
- Store apps update by themselves in the background.
- To uninstall, open Bazaar's *Installed* tab, which works like Windows' *Apps & features*.

Most apps you know are there: Discord, Spotify, OBS, VLC, GIMP, Blender, Zoom, Telegram, Signal, Obsidian, and many more.

## Downloaded a file? Double-click it

| You downloaded | What happens when you double-click it |
|---|---|
| A **Store link** (`.flatpakref`) | The Store opens on that app. Press Install. |
| A **Windows program** (`.exe`, `.msi`) | SparkOS opens it in **Spark Run**: run it once, or install it as an app with its own menu entry. The first time, Spark Run downloads Wine (about 130 MB, no admin password). Not every Windows program works. For **Windows games**, install Steam or Heroic from the Store and add the game there instead. |
| An **AppImage** (`.AppImage`) | SparkOS asks once: **Add to the app menu** moves it to your *Applications* folder (`~/Applications`) and adds it to the menu, or **Run once** starts it from where it is. To remove an added AppImage, right-click it in the menu and choose **Remove from this PC**; that deletes the file and its menu entry (its settings stay). Updates come from the app itself, if it has them. Only open AppImages from people you trust: SparkOS can't check what they do. |
| A **Fedora/Red Hat installer** (`.rpm`) | SparkOS asks whether to install it and asks for your password, then installs it into the system. It's ready after a restart. These don't update by themselves, so prefer the Store version if there is one. |
| An **Ubuntu/Debian installer** (`.deb`) | SparkOS explains it can't install this kind of file and offers to open the Store. Most apps are there. Otherwise look on the app's website for a Flatpak, AppImage or `.rpm` download. |

## Good to know

- **Your apps sit apart from the system.** That's why updates are safe and a bad system update can be undone from the boot menu. It's also why a few Windows habits don't apply: there's no "install for all users" wizard and no registry.
- **SparkOS starts clean.** It ships only its own apps (Soot, FreeSuite, Spark Snip, Spark Media). Steam, Heroic (Epic, GOG, Amazon), Lutris (Battle.net, EA and others), Discord, Chrome and everything else install from the Store in a click.
- **Your own Linux builds** (Soot, FreeSuite, Spark Snip, Spark Media) come with SparkOS. Androidbox installs from its release with `bash packaging/linux/install.sh --user` (see the switching guide).
- **Developer tools** (Node, Python, GitHub CLI, JDK) install with `sparkos-dev-setup`, which is the one place a command is the easier way.
