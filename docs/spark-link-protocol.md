# Spark Link protocol (draft 1)

Spark Link connects a phone and a SparkOS PC on the same network, without any outside service:
no account, no cloud, no relay server. The PC side is the Spark Link app in SparkOS
(`files/spark-link/`); the phone side lives in Soot's Android app (`WolkNet/phone`, a "Link to PC"
section). Both follow this document. Change it in one PR with both sides, and bump the version.

This is a draft: the two sessions building it may refine details, but must agree, and record any
change here.

## Discovery

- The PC announces `_sparklink._tcp` over mDNS (Avahi, already in SparkOS) with TXT records
  `v=1`, `id=<device id>`, `name=<PC name>`. Port: 47100 by default (TCP).
- The phone browses for it with Android's `NsdManager`. If mDNS is blocked on a network, the phone
  can type the PC's address (shown in the PC app).

## Pairing (once per phone)

- Each device has a long-term key pair (Ed25519) and a self-signed TLS certificate made from it,
  created on first run and kept on the device (PC: `~/.local/share/spark-link/`, Android: the app's
  private storage / Keystore).
- The PC app shows a QR code: `sparklink://pair?v=1&host=<ip>&port=<port>&id=<pc id>&fp=<sha256 of
  the PC's certificate>&code=<6-digit one-time code>`.
- The phone scans it, connects over TLS checking the PC's certificate fingerprint `fp`, and sends
  `pair` with the one-time code, its own id, name and certificate fingerprint. The PC asks the user
  to confirm ("Pair with Pixel 8?"), then stores the phone's fingerprint. From then on both sides
  pin each other's certificate (mutual TLS); nothing else is trusted.
- Unpair from either side deletes the stored fingerprint.

## Connection

- TLS 1.3, both sides pinned as above. Messages are JSON objects, one per frame:
  a 4-byte big-endian length, then UTF-8 JSON. Binary file data follows in its own frames
  (see `file.chunk`).
- Every message: `{"type": "...", "id": <int, per sender>, ...}`. Replies carry `"re": <id>`.
- `hello` on connect: `{"type":"hello","v":1,"id":0,"device":{"id":..., "name":..., "kind":"pc"|"phone"},"features":[...]}`.
  Only features both sides list are used.
- `ping` / `pong` every 30 s; reconnect with backoff (1, 2, 5, 10, 30 s) after a drop.

## Features (version 1)

| Feature | Messages | Notes |
|---|---|---|
| Send a tab / link | `url.open {url}` | Opens in Soot (PC) or Soot (phone). The obvious browser feature. |
| Shared clipboard | `clipboard.set {text}` | Text only in v1. Off by default; the user switches it on. |
| Files | `file.offer {name,size,sha256}` → `file.accept`/`file.reject`, then `file.chunk {seq,last}` + binary frame, `file.done` | Saved to Downloads; the receiver confirms each transfer unless "always accept from this device" is on. |
| Phone notifications on the PC | `notify.posted {app,title,text,key}`, `notify.removed {key}` | Phone side only with the user's notification-access permission. Read-only in v1 (no replies). |
| Battery | `battery {level,charging}` | Shown in the PC app. |
| Find my phone | `ring` | Phone rings at full volume until tapped. |

## Privacy and limits

- Everything stays on the local network. No telemetry, no outside servers.
- Each feature can be switched off on each side; the phone's background connection can be turned
  off entirely in Soot's settings.
- Not in v1: SMS, calls, media control, remote input, screen mirroring.
