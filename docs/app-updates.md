# Live app updates

A change to a Spark app ships as a signed release of that app alone. Spark Update installs it
while the PC runs: no reboot, no image rebuild. The image keeps its own copy of every app as
the fallback. Reboots stay for real OS changes.

Status: built and tested with a throwaway key and a local web server. Nothing is released
until the `SIGNING_SECRET` secret is set and the `app-updates` workflow has run once. Not yet
tried on a booted SparkOS.

## Pilot apps

Spark Calc, Spark Clock, Spark Edit, Spark Emoji, Spark Notes and Spark Space. They are
self-contained user-space apps with no root helper, no daemon and no polkit action, so a bad
bundle can at worst break the app, and the built-in copy is one click away.

An app opts in with `"live_update": true` and `"system_api": N` in its `spark-app.json`.

Spark Clock 0.2.0 is the first pilot app with a root part: its wake-from-sleep helper and polkit action ship in the image (`files/scripts/spark-clock-wake.sh`), outside its bundle, and it raised `system_api` to 2 for that.

## How it works

1. A push to main that raises an opted-in app's `version` runs `.github/workflows/app-updates.yml`.
2. It waits for the app's own check (its workflow: tests on Fedora and inside the image, English
   and French) to pass on those exact app files, builds a deterministic `<slug>-<version>.tar.gz` from
   the app's `install.sh --stage`, and publishes it as release `app-<slug>-<version>`.
3. It then signs a new index and uploads it as `index.json` on release `apps-index`. Bundles go
   up first, so the index never names a file that isn't there. A weekly run signs it again so it
   never reaches its 30 day expiry.
4. On the PC, `spark-apps-update.timer` (10 minutes after boot, then hourly) runs the root
   service `/usr/libexec/spark-apps-update`. It downloads the index, checks it, downloads each
   newer bundle, checks the hash, extracts it safely and moves it into
   `/var/lib/spark-apps/<slug>/<version>/`.
5. `/usr/bin/spark-<app>` runs `launch.py`, which picks the live copy or the built-in one at
   every start. A running window keeps its version until it is closed.

The index is one JSON envelope: `{"format":1,"payload":"<json text>","signature":"<base64>"}`.
The payload holds `serial`, `issued`, `expires` and, per app, `version`, `system_api`, `url`,
`sha256` and `size`.

## Trust chain

1. The release workflow signs the index with SparkOS's cosign key (`cosign sign-blob`, secret
   `SIGNING_SECRET`). That key already signs the image.
2. The public half, `cosign.pub`, is baked into the image at `/etc/pki/containers/sparkos.pub`
   and copied to `/usr/share/spark-apps/index-key.pub`. Only an image update (itself signed and
   verified by bootc) can change it.
3. The root service checks the signature with `openssl dgst -sha256 -verify`, then pins each
   bundle to the sha256 and size in the signed payload. Python stdlib and openssl only.

Why reuse the image key: one key to guard and rotate, already in the image, no new secret. The
cost is that a leaked image key also lets someone sign app updates. That is not a new power:
the same key already controls the whole OS. If the owner wants the two split later, a second key
means a second file in the image and a second secret; the client only reads one path.

The client refuses an index when: the signature is bad, the serial is lower than the last one
seen (rollback), it has expired (freeze), or the file isn't well formed. It refuses a bundle
when: the URL doesn't start with `https://github.com/Wolklaw/sparkos/releases/download/`, the
size or sha256 differ, the version isn't newer than the installed one, the archive holds an
absolute path, `..`, a link or a device, or the manifest inside disagrees with the index.

## Where code runs from

- Root code (daemons, pkexec helpers, systemd units, polkit, udev, `/usr/libexec`) always comes
  from the image. Bundles never carry any.
- Live code sits in `/var/lib/spark-apps/`, owned by root, written only by the root service after
  verification: extracted to a temp directory next to the target, checked, then renamed into
  place. Python files are recompiled by root with hash-checked bytecode.
- `choose.select` uses the live copy only when it is root-owned, not group or world writable,
  free of symlinks, newer than the built-in version, its manifest version matches, its
  `system_api` equals the one recorded in the image (`/usr/share/spark-apps/<slug>.json`) and the
  entry file exists. Any doubt means the built-in copy.

## What still needs an image update

Anything outside the app's own folder: a new package, a root helper, a systemd unit, a polkit
rule, a udev rule, a menu entry or icon outside the bundle, a changed launcher. Bump the app's
`system_api` in the same change. An old live copy then stops matching and the built-in copy
(newer, from the new image) runs. Bundles with the new number are used only after the image that
has it is booted.

## Rollback and switching

Spark Update has an App updates page. Per app it shows built-in and live versions, which one runs,
and buttons to use the built-in copy, the live copy, or update now. Command line:
`systemctl start spark-apps-now@use-builtin:spark-calc.service` (also `use-live:` and
`use-previous:`, and `spark-apps-now@update.service`). A polkit rule allows only these units
without a password. The service keeps the previous live version, so `use-previous` is instant.
A new live version is not used for an app that is running; it starts with the next launch.

## Failure modes

| What happens | Result |
|---|---|
| Offline, or GitHub down | Nothing changes; the page says "offline"; apps keep their current copy |
| Bad signature, bad hash, bad archive | Refused; recorded as `refused` with the reason; nothing installed |
| Expired index (the weekly run stopped) | Refused; installed live copies keep working |
| Serial lower than the last seen | Refused (rollback attempt) |
| Live copy damaged or edited | Fails the launcher checks; built-in runs |
| Live copy crashes | Open the App updates page and use the built-in copy or the previous one |
| `SIGNING_SECRET` missing | The release run fails before publishing; PCs see no change |
| Image updated past a live version | The newer built-in wins; the old live copy is ignored and later cleaned up |

## Operating it

- First release: set `SIGNING_SECRET` (the private key matching `cosign.pub`) and
  `COSIGN_PASSWORD` handling as the image build does, then run `app-updates` by hand
  (workflow_dispatch). It publishes every opted-in app at its current version.
- A normal release: raise `version` in the app's `spark-app.json`. A version is released once;
  rebuilding the same number with different bytes fails the run.
- Pull requests run the same pipeline as a dry run with a throwaway key and publish nothing.
- Tests: `cd files/spark-apps && python3 -m unittest discover -s tests`. The end-to-end test
  starts a local web server and signs with a throwaway key.
- `cosign sign-blob` itself has not been run here (the flags are written from its documentation).
  The workflow checks its output with the PC's own verifier before publishing anything.
