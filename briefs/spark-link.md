# Spark Link (PC side)

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-link/`, `install.sh` with `--deps` and `--user`, `spark-app.json`,
`--self-test`, tests, workflow, build step `files/scripts/spark-link.sh`). Don't edit
`recipes/recipe.yml` or `boot-test.yml`; the main session wires it in and decides with the owner
when KDE Connect leaves the image.

## Why

KDE Connect is SparkOS's phone link today: another project's app on both the PC and the phone.
The owner wants as few ties to other projects as possible ([PLAN.md, Independence roadmap](../PLAN.md)).
Spark Link is SparkOS's own, and its phone side lives in Soot's Android app (the owner's idea), so
both ends are the owner's.

## The protocol

[docs/spark-link-protocol.md](../docs/spark-link-protocol.md) is the shared spec. Another session is
building the phone side in Soot's app (`E:\Personal Projects\WolkNet\phone`) at the same time. You
own the spec: if a detail needs to change, change it in that doc in your PR and say so clearly, so
the phone side can follow. Keep it simple and secure: pinned mutual TLS after QR pairing, no
outside servers.

## What it does

- A small background service (systemd user unit, started at login, near-zero CPU when idle) that
  announces itself over mDNS, keeps the paired phone connected, and handles the v1 features:
  links opening in Soot, the shared clipboard (off by default), files into Downloads, phone
  notifications shown as Plasma notifications, battery, and "Find my phone".
- The window: pairing (QR code, the address for typing, the confirmation), paired devices
  (battery, last seen, unpair), feature switches, and "Send files" / "Send a link" / "Ring".
- Dolphin right-click "Send to phone", and Soot's "send this tab to phone" if Soot supports a hook
  (say in the PR what Soot would need).
- Firewall: open the Spark Link port in the image's firewalld config (check whether firewalld is
  on in SparkOS), only on the local network zone.

## Testing

The phone side isn't in CI. Write a small reference client in Python (in `tests/`) that speaks the
protocol like the phone will, and test pairing, reconnecting, each feature and the failure cases
(wrong code, wrong fingerprint, unpaired device) against the real service, in Fedora and inside
`ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`).

## Done when

CI passes, the protocol doc matches what's built, and a PR from `spark-link` is open for the owner,
saying what still needs a real phone to verify.
