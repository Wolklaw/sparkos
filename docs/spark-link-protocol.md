# Spark Link protocol (draft 2)

Spark Link connects a phone and a SparkOS PC on the same network, without any outside service:
no account, no cloud, no relay server. The PC side is the Spark Link app in SparkOS
(`files/spark-link/`); the phone side lives in Soot's Android app (`WolkNet/phone`, a "Link to PC"
section). Both follow this document. Change it in one PR with both sides, and bump the version.

The reference for what the PC accepts is `files/spark-link/tests/linkclient.py`: a small Python
client that behaves the way the phone must, run against the real PC service in CI.

## What changed from draft 1

Agreed between the PC side and the phone side sessions on 2026-11-20:

- **Keys are ECDSA P-256, not Ed25519.** Soot's app supports Android 11 and up, and Android's TLS
  stack can't reliably use Ed25519 keys before Android 14. P-256 works on every Android version
  and in Python's `ssl`.
- **The pairing connection carries no client certificate, and `pair` carries the phone's whole
  certificate** (draft 1 sent only its fingerprint). Python's `ssl` (the PC side) can't accept an
  unknown client certificate during the handshake and decide later, so the phone pairs without
  one, and the PC pins the certificate it receives inside the TLS channel it has already pinned.
- **After `pair.ok` the PC closes the connection** and the phone reconnects with its certificate.
  Every connection that carries features is mutual TLS, with no exception.
- **An unknown phone certificate fails the TLS handshake**; the PC can't send an "unpaired"
  message (see Connection).
- Filled in: feature names, message ids, `error`, `file.cancel`, reject reasons, the binary frame
  rule, size limits, timeouts, the 75 s idle limit, address limits, the typed-address fallback with
  a key check, and `&name=` in the QR link. A side may send `hello` again to update its features.

## Discovery

- The PC announces `_sparklink._tcp` over mDNS (Avahi, already in SparkOS) with TXT records
  `v=1`, `id=<PC id>`, `name=<PC name>`. Port: 47100 by default (TCP).
- The PC only listens, and only announces, while at least one phone is paired or the pairing
  screen is open.
- The phone browses for it with Android's `NsdManager`. If mDNS is blocked on a network, the phone
  can use the pairing link or the typed address (both shown in the PC window, see Pairing).

## Identity

- Each device has a long-term ECDSA P-256 key pair and a self-signed X.509 v3 certificate made
  from it (signature `ecdsa-with-SHA256`), created on first run and kept on the device (PC:
  `~/.local/share/spark-link/`, files `key.pem` and `cert.pem`, mode 0600; Android: the app's
  Keystore).
- **Fingerprint (`fp`)**: lowercase hex SHA-256 of the certificate's DER bytes, 64 characters, no
  colons.
- **Device id**: 1 to 64 characters of `A-Z a-z 0-9 _ -` (both sides use 32 random hex
  characters). **Name**: up to 64 characters; the PC strips control characters.
- The phone's certificate, so OpenSSL on the PC accepts it as its own trust anchor:
  `notBefore` at least a day in the past (OpenSSL checks dates; clocks drift), `notAfter` far
  ahead (2099 is fine), no `extendedKeyUsage` (or one that includes `clientAuth`), `keyUsage`
  absent or including `digitalSignature`.

## Pairing (once per phone)

1. The user opens "Pair a phone" in the PC window. The PC makes a 6-digit one-time code, valid
   5 minutes, and shows:
   - a QR code of the **pairing link**:
     `sparklink://pair?v=1&host=<ip>&port=<port>&id=<PC id>&fp=<PC fp>&code=<code>&name=<PC name, URL-encoded>`
     (`name` is optional for the phone to read);
   - the same link as text the user can copy (the phone also accepts it pasted or opened from
     another app);
   - for typing by hand: the address (`192.168.1.23:47100`), the code, and the **key check**: the
     first 16 hex characters of the PC's fp in upper case, in groups of 4 (`3F2A 91C0 7D11 4E8B`).
2. The phone connects to `host:port` with TLS 1.3 **without a client certificate** and checks
   that the SHA-256 of the PC's certificate equals `fp`. If the user typed the address (no `fp`),
   the phone shows the first 16 hex characters of the certificate it received, grouped the same
   way, and sends the code only after the user confirms they match what the PC shows. This keeps
   a machine in the middle on the local network out.
3. Within 10 s the phone sends, as its first frame:
   `{"type":"pair","id":1,"v":1,"code":"123456","device":{"id":"…","name":"Pixel 8","kind":"phone"},"cert":"<base64 DER>"}`
   (`cert` is the phone's certificate, standard base64 with padding). The PC computes its fp.
4. The PC asks the user to confirm ("Pair with Pixel 8?"). The phone waits up to 120 s.
5. The PC answers one of:
   - `{"type":"pair.ok","re":1,"device":{"id":"…","name":"…","kind":"pc"}}`
   - `{"type":"pair.fail","re":1,"reason":"code"|"declined"|"timeout"|"not-pairing"|"busy"}`

   and closes the connection either way. `code`: wrong code. `not-pairing`: the pairing screen
   isn't open or the code expired. `busy`: another phone is being confirmed.
6. After `pair.ok` the phone stores the PC's fp, id and name, and reconnects at once with its
   client certificate (see Connection). From then on both sides pin each other's certificate;
   nothing else is trusted.

Limits on the PC: the code works once (a confirmed or declined pairing ends the session); five
wrong codes cancel the pairing session and the user must start again; an unauthenticated
connection may send nothing but `pair`.

**Unpair** from either side deletes the stored certificate. Over a live connection it's
`{"type":"unpair","id":n}`: the receiver deletes the sender's certificate too, and the connection
closes.

## Connection

- The PC is always the TLS server on its port; the phone is always the client, and only the
  phone reconnects, with backoff 1, 2, 5, 10, 30 s (then every 30 s) after a drop.
- TLS 1.3 only. The phone presents its certificate; the PC requests one (its CertificateRequest
  lists no CA names, so the phone's key manager offers its certificate regardless of issuers),
  trusts only the certificates of paired phones, and checks the fp against its list. The phone
  checks the PC's certificate fp against the one it stored at pairing.
- **Unknown phone certificate**: the PC's TLS stack rejects the handshake with an alert
  (`certificate_unknown`, `bad_certificate`, `unknown_ca` or similar). If the PC's fp checked out
  and the handshake or the first read then fails with such an alert (twice in a row, so flaky
  Wi-Fi doesn't trigger it), the phone shows that the PC no longer knows this phone and offers to
  pair again.
- The PC accepts connections only from private, link-local and loopback addresses, plus
  Tailscale's 100.64.0.0/10 while the PC itself has a Tailscale address, and at most 8
  at a time. A newer connection from the same phone replaces the older one.
- **Frames**: a 4-byte big-endian length, then the payload, at most 1 MiB (1,048,576 bytes).
  A payload is UTF-8 JSON (one object), except the one binary frame after each `file.chunk`.
  A bigger frame, invalid JSON or a non-object is a protocol error: the receiver closes the
  connection.
- **Messages**: `{"type": "...", "id": <int>, ...}`. `id` counts up per sender (any start).
  Replies carry `"re": <id of the message answered>`.
- **hello**: the phone sends it first after the handshake, the PC answers with its own:
  `{"type":"hello","v":1,"id":0,"device":{"id":"…","name":"…","kind":"pc"|"phone"},"features":["url","files",…]}`.
  The PC closes the connection if the phone's `device.id` isn't the one it paired with. Only
  features both sides list are used. The PC's `hello` may add `"addresses":["100.x.y.z",…]`: its
  Tailscale IPv4 addresses (100.64.0.0/10), empty or absent when it isn't on a tailnet. The phone
  keeps them and tries them, on the same port, after the local addresses it knows; it does not
  save a Tailscale address as its last local one.
  Either side may send `hello` again at any time to update
  its list (the user switched clipboard on, say); the latest list counts.
- **ping**: the phone sends `{"type":"ping","id":n}` every 30 s; the other side answers
  `{"type":"pong","id":m,"re":n}`. The PC may ping too; always answer. Either side drops the link
  after 75 s with nothing received.
- **error**: `{"type":"error","id":n,"re":<id>,"reason":"bad-message"|"feature-off"|"too-big"}`
  when a side refuses a message. Unknown message types are ignored (no error), so either side can
  add messages later.

## Features (version 1)

Feature names in `hello`: `url`, `clipboard`, `files`, `notify`, `battery`, `ring`.

| Feature | Messages | Notes |
|---|---|---|
| `url`: send a tab or link | `url.open {url}` | Either way. `http` and `https` only, up to 8 KiB. Opens in Soot on the PC (the default browser if Soot isn't there) and in Soot on the phone. |
| `clipboard`: shared clipboard | `clipboard.set {text}` | Either way, text only, the frame within 1 MiB. **Off by default**: the PC lists `clipboard` only after the user switches it on. A side never sends back text it just received. |
| `files` | `file.offer`, `file.accept`/`file.reject`, `file.chunk` + binary frame, `file.done`, `file.cancel` | Either way; see below. Saved to Downloads. |
| `notify`: phone notifications on the PC | `notify.posted {app,title,text,key}`, `notify.removed {key}` | Phone to PC, only with the user's notification-access permission. `app` is the app's label, `key` an opaque string up to 256 characters, `text` may be empty. Read-only in v1 (no replies). The PC shows them as Plasma notifications, as plain text. |
| `battery` | `battery {level,charging}` | Phone to PC, right after `hello` and on each change. `level` 0-100, `charging` true/false. Shown in the PC window; the PC warns once at 15 % and below while not charging. |
| `ring`: find my phone | `ring` | PC to phone: the phone rings at full volume until tapped. No reply. If the phone sends `ring`, the PC plays a sound and shows a notification. |

### Files

1. Sender: `{"type":"file.offer","id":7,"name":"photo.jpg","size":123456,"sha256":"<lowercase hex>"}`.
   `name` is a bare file name; the receiver strips any path, control characters and leading dots,
   and never overwrites a file (it adds ` (1)`, ` (2)`, ...). Size up to 16 GiB.
2. Receiver: `{"type":"file.accept","re":7}` or
   `{"type":"file.reject","re":7,"reason":"declined"|"off"|"space"|"timeout"|"busy"}`.
   The receiver confirms each transfer unless "always accept files from this device" is on for
   the sender. The PC gives the user 120 s, then rejects with `timeout`.
3. Sender: `{"type":"file.chunk","file":7,"seq":0,"last":false}` followed immediately by exactly
   one binary frame of 1 to 65,536 bytes, then `seq` 1, 2, ... in order. The last chunk has
   `"last":true` (and may be shorter). A 0-byte file is one chunk with `last:true` and a 0-length
   binary frame.
4. Receiver, after the last chunk, checks the size and the SHA-256:
   `{"type":"file.done","re":7,"ok":true}` (or `"ok":false`; it then deletes what it wrote).
5. `{"type":"file.cancel","file":7}` from either side at any time ends the transfer; the receiver
   deletes the partial file.

Several transfers may run at once; chunks of different files may interleave, but each binary
frame directly follows its own `file.chunk`.

## Privacy and limits

- Everything stays on the local network, or on the owner's own tailnet when both ends use
  Tailscale. No telemetry, no outside servers of Spark Link's own.
- Each feature can be switched off on each side; the phone's background connection can be turned
  off entirely in Soot's settings.
- The PC never logs clipboard text, notification contents, file contents or pairing codes.
- Not in v1: SMS, calls, media control, remote input, screen mirroring.
