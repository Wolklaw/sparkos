# Spark Firewall

The firewall in plain words: on or off, which zone each network is in, and the few things a person actually opens a firewall for (Steam Remote Play, Spark Link, file sharing). It replaces firewall-config. Source: [files/spark-firewall](../files/spark-firewall). In the SparkOS image.

Status: built 2026-11-23, version 0.1.0. Tested against a fake runner and firewalld output recorded on the owner's PC, and the window was opened and the self-test run on that PC with only read commands. **Nothing has been written to the real firewall yet.** See "Not tried on the real firewall".

## An app, not a Settings page

Spark Firewall is its own app, not a page in Spark Settings.

- **It needs root, and Settings doesn't.** Settings is a router: its pages read and write the user's own settings, or hand off to KDE's modules. A firewall change needs a root helper, a polkit action and a list of operations the helper accepts. That is the shape of Spark Controller, which is also its own app for the same reason. Putting a root helper inside Settings would make every Settings page part of a privileged install.
- **It has its own state to show.** A firewall has a running state, a boot state, zones, networks and rules. That is a window of its own, not one row among Wi-Fi, sound and display.
- **It is how people look for it.** Someone told to "open the firewall for Steam" searches for Firewall. firewall-config was an app; the menu entry it leaves should be one too.
- **Settings can still point at it.** A Network page in Settings can link to `spark-firewall` later. That is a link, not a second implementation, and is not built here.

## What it does

Three tabs, with a bar at the bottom that shows only while there are unsaved changes (Apply, Revert). Nothing is changed until Apply.

- **Overview.** Four tiles: running or stopped, on at boot or not, the default zone, how many things are open. A button turns the firewall on or off (turning off asks to be clicked twice). A banner says plainly when the firewall is stopped or when the zone leaves everything above port 1024 open. A table of the PC's networks with a zone picker for each, and a picker for the default zone.
- **Rules.** One switch per plain-language rule, for the zone chosen at the top: Steam Remote Play, Steam game transfers on the home network, Spark Link, KDE Connect, Be found by name on the network, Windows file sharing, Remote login (SSH), Syncthing, Warpinator, and Web server (HTTP and HTTPS). A rule is shown only if firewalld has the service for it. Each rule says what it opens (the ports) and its state: open, closed, covered by the zone, or waiting for Apply.
- **Ports.** Everything the zone opens, as services and ports, with Remove. Add a port (a number or a range, TCP or UDP).

English and French, following the PC's language (`SPARK_LANG` overrides).

## Zones, and the Fedora Workstation catch

Fedora Workstation and Kinoite ship with the default zone `FedoraWorkstation`, which already opens every port from 1025 to 65535 (TCP and UDP) to the network. In that zone a rule for a high port (Steam Remote Play at 27036, for instance) changes nothing, because it is already open. This is firewalld's own default, not something the app invented.

The app says so instead of showing a switch that does nothing: such a rule reads "covered by the zone", and the Overview banner says the zone leaves ports 1025 and up open. The way out is a stricter zone for a network (public, home, work, trusted, block) and the rules then take effect. **This is the owner's decision**: leave FedoraWorkstation as the default (nothing changes on first run), or make `public` the default so the rules mean something. The app does not change it by itself.

A network's zone is saved with NetworkManager (`nmcli connection modify uuid ... connection.zone`) so it comes back after a reconnect, plus a live `--change-interface` so it applies at once. A network that NetworkManager doesn't manage gets a permanent firewalld change instead.

## How it changes the firewall

The window never writes. To apply, it sends a list of operations to `pkexec /usr/libexec/spark-firewall-helper apply` (JSON on standard input, polkit action `dev.wolklaw.SparkFirewall.configure`, `auth_admin_keep`: one password per session, like Spark Controller).

The helper accepts five operations and nothing else: add or remove a service in a zone, add or remove a port in a zone, set the default zone, set a network's zone, turn the firewall on or off. Every name is checked against a strict pattern (letters, digits, `-`, `_`, `.`, never a leading dash), a port is a number or range 1-65535 with tcp or udp, a connection is a UUID. It builds each command as an exact list for `firewall-cmd`, `nmcli` or `systemctl` and runs it with no shell. It starts with Python `-I` so nothing from the user's environment is imported as root. It refuses a list that is too large, has an unknown operation, or mixes turning the firewall off with other changes. It stops at the first failure and says which one failed. "Already enabled" and "not enabled" are not failures. Service and port changes are written with `--permanent` and followed by one `--reload`, so what the window shows is what survives a reboot.

Reading uses no helper: `firewall-cmd` queries (state, zones, services, a zone's contents) and `nmcli connection show`, as the user. When firewalld is stopped, or not installed, the window says so and offers to turn it on.

Rejected: calling firewalld's D-Bus API directly from the window. firewalld's own polkit rules would then govern, and the window could not group several changes behind one password or offer a revert. A helper with a short, checked operation list is easier to read and to test with a fake runner.

## Tests

Unit tests run the helper and the reading code against a fake runner that records every command line and answers from output recorded on the owner's PC. They check that bad names, bad ports and unknown operations are refused before any command runs, the exact command lines for each operation, one reload for many changes, stop-at-first-failure, and that a read never runs a command that writes. Window tests (Xvfb, English and French) open every tab, check that the text fits, and check that a change waits for Apply and is sent once, with a fake sender instead of pkexec. `--self-test` only reads the firewall and checks the operation checks and the French table. CI runs the install in a Fedora container, the tests twice, and the uninstall. The boot test checks the files, the self-test, that the helper refuses a bad operation, and that firewall-config is hidden but installed.

## Not tried on the real firewall

Everything below is written to firewalld's documented behaviour and tested only against fakes (reads were checked on the owner's PC). The first real Apply is the owner's.

- Each write: `--permanent --add-service`, `--add-port`, `--set-default-zone`, `--change-interface`, and `systemctl enable/disable --now firewalld`.
- The `--reload` after a permanent change, and that it keeps the zone of each interface.
- `nmcli connection modify ... connection.zone` on the owner's connections (eno1, tailscale0), and Tailscale's interface, which NetworkManager may not manage.
- The polkit prompt and `pkexec` with the helper path, and cancelling it.
- Switching a network from FedoraWorkstation to a stricter zone with a live connection (it cannot cut a Remote Desktop or SSH session unless that service is closed in the new zone, so the app should be tried from the PC itself first).
- Services that only exist when a package ships them (kdeconnect, warpinator, syncthing): their rules hide when the service is missing.

Version 1.0.0 after the first real Apply works.

## Later

A log of what was blocked (firewalld's denied-packets log), rich rules for "only from my phone", a Settings link, and removing firewall-config from the image after one release hidden.
