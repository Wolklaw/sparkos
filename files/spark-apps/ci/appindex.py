#!/usr/bin/env python3
"""Release tooling for live app updates (CI runs it; tests run it too). Standard library only.

    appindex.py changed  --apps-dir files --index CURRENT|none           slugs to release (JSON list)
    appindex.py bundle   --slug S --stage DIR --out FILE.tar.gz          deterministic bundle
    appindex.py build    --apps-dir files --out DIR SLUG...              stage + bundle + entries.json
    appindex.py payload  --index CURRENT|none --entries FILE.json --out FILE [--days N] [--now T]
    appindex.py envelope --payload FILE --signature FILE --out FILE
    appindex.py verify   --index FILE --key PUB                          same checks as a PC

`changed` compares each opted-in app's spark-app.json version with what the current signed index
lists (apps not in it are new). `bundle` packs the staged tree (install.sh --stage) so the same
inputs always give the same bytes (sorted names, no times, no owners, fixed gzip header).
`payload` writes the index payload: serial = the current one + 1, dates, and every app's entry
(entries not touched are carried over from the current index). `envelope` joins payload and
signature in the one-file form the clients read. `verify` runs the client's own code."""

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkapps import INDEX_FORMAT, INDEX_TYPE, URL_PREFIX, index as index_mod   # noqa: E402
from sparkapps.paths import valid_slug, version_key                  # noqa: E402



def read_current(path):
    """The payload dict of the signed index at path (not verified here: CI fetched it from our
    own release, and the clients verify), or None for 'none' / a missing file."""
    if not path or path == 'none' or not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        envelope = json.load(f)
    return json.loads(envelope['payload'])


def opted_in(apps_dir):
    """slug -> its spark-app.json, for every app folder with live_update true."""
    found = {}
    for name in sorted(os.listdir(apps_dir)):
        manifest = os.path.join(apps_dir, name, 'spark-app.json')
        if not valid_slug(name) or not os.path.isfile(manifest):
            continue
        with open(manifest, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('live_update') is True:
            if data.get('slug') != name:
                raise SystemExit(f"{manifest}: slug isn't {name}")
            version_key(data.get('version'))
            if not isinstance(data.get('system_api'), int) or data['system_api'] < 1:
                raise SystemExit(f"{manifest}: system_api must be a whole number")
            found[name] = data
    return found


def changed(apps_dir, current):
    listed = (current or {}).get('apps', {})
    out = []
    for slug, data in opted_in(apps_dir).items():
        have = listed.get(slug)
        if have is None or version_key(data['version']) > version_key(have['version']):
            out.append(slug)
        elif version_key(data['version']) < version_key(have['version']):
            raise SystemExit(f"{slug}: version {data['version']} is older than the released "
                             f"{have['version']}")
    return out


def build_bundle(stage, out):
    """Deterministic .tar.gz of everything under stage (paths relative to it)."""
    names = []
    for base, dirs, files in os.walk(stage):
        dirs.sort()
        rel = os.path.relpath(base, stage)
        for name in sorted(dirs) + sorted(files):
            names.append(os.path.normpath(os.path.join(rel, name)))
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(names):
            full = os.path.join(stage, rel)
            if os.path.islink(full):
                raise SystemExit(f"{rel} is a link: not allowed in a bundle")
            info = tarfile.TarInfo(rel)
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, '', ''
            if os.path.isdir(full):
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            elif os.path.isfile(full):
                info.size = os.path.getsize(full)
                info.mode = 0o644
                with open(full, 'rb') as f:
                    tar.addfile(info, f)
            else:
                raise SystemExit(f"{rel} isn't a plain file or folder")
    with open(out, 'wb') as f:
        with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0, compresslevel=9) as gz:
            gz.write(raw.getvalue())


def release_tag(slug, version):
    return f"app-{slug}-{version}"


def build_apps(apps_dir, out_dir, slugs):
    """For each slug: run the app's own `install.sh --stage`, pack it, and describe it the way
    the index lists it. Writes <out>/<slug>-<version>.tar.gz and <out>/entries.json."""
    manifests = opted_in(apps_dir)
    os.makedirs(out_dir, exist_ok=True)
    entries = {}
    for slug in slugs:
        if slug not in manifests:
            raise SystemExit(f"{slug} doesn't take live updates")
        version = manifests[slug]['version']
        with tempfile.TemporaryDirectory(prefix='stage-') as tmp:
            stage = os.path.join(tmp, 'tree')
            subprocess.run(['bash', os.path.join(apps_dir, slug, 'install.sh'), '--stage', stage],
                           check=True, stdin=subprocess.DEVNULL)
            if not os.path.isfile(os.path.join(stage, 'spark-app.json')):
                raise SystemExit(f"{slug}: the staged tree has no spark-app.json")
            bundle = os.path.join(out_dir, f"{slug}-{version}.tar.gz")
            build_bundle(stage, bundle)
        with open(bundle, 'rb') as f:
            data = f.read()
        entries[slug] = {"version": version, "system_api": manifests[slug]['system_api'],
                         "url": f"{URL_PREFIX}{release_tag(slug, version)}/"
                                f"{os.path.basename(bundle)}",
                         "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    with open(os.path.join(out_dir, 'entries.json'), 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=1, sort_keys=True)
        f.write("\n")
    return entries


def make_payload(current, entries, *, now, days):
    apps = dict((current or {}).get('apps', {}))
    apps.update(entries)
    serial = int((current or {}).get('serial', 0)) + 1
    return {"type": INDEX_TYPE, "format": INDEX_FORMAT, "serial": serial,
            "issued": index_mod.format_date(now),
            "expires": index_mod.format_date(now + days * 86400),
            "apps": {slug: apps[slug] for slug in sorted(apps)}}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('changed')
    a.add_argument('--apps-dir', required=True)
    a.add_argument('--index', default='none')
    a = sub.add_parser('bundle')
    a.add_argument('--slug', required=True)
    a.add_argument('--stage', required=True)
    a.add_argument('--out', required=True)
    a = sub.add_parser('build')
    a.add_argument('--apps-dir', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('slugs', nargs='*')
    a = sub.add_parser('payload')
    a.add_argument('--index', default='none')
    a.add_argument('--entries', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--days', type=int, default=30)
    a.add_argument('--now', type=int, default=None)
    a = sub.add_parser('envelope')
    a.add_argument('--payload', required=True)
    a.add_argument('--signature', required=True)
    a.add_argument('--out', required=True)
    a = sub.add_parser('verify')
    a.add_argument('--index', required=True)
    a.add_argument('--key', required=True)
    args = parser.parse_args(argv)

    if args.cmd == 'changed':
        print(json.dumps(changed(args.apps_dir, read_current(args.index))))
    elif args.cmd == 'bundle':
        if not valid_slug(args.slug):
            raise SystemExit("bad slug")
        build_bundle(args.stage, args.out)
    elif args.cmd == 'build':
        for slug, entry in build_apps(args.apps_dir, args.out, args.slugs).items():
            print(f"{slug} {entry['version']} {entry['size']} bytes sha256 {entry['sha256']}")
    elif args.cmd == 'payload':
        with open(args.entries, encoding='utf-8') as f:
            entries = json.load(f)
        now = int(time.time()) if args.now is None else args.now
        payload = make_payload(read_current(args.index), entries, now=now, days=args.days)
        index_mod.parse_payload(payload)       # the same checks a client makes
        with open(args.out, 'w', encoding='utf-8', newline='') as f:
            f.write(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    elif args.cmd == 'envelope':
        with open(args.payload, encoding='utf-8', newline='') as f:
            text = f.read()
        with open(args.signature, encoding='utf-8') as f:
            signature = ''.join(f.read().split())
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(index_mod.make_envelope(text, signature))
    elif args.cmd == 'verify':
        with open(args.index, 'rb') as f:
            index = index_mod.load(f.read(), args.key)
        print(f"ok: serial {index.serial}, {len(index.apps)} app(s), expires "
              f"{index_mod.format_date(index.expires)}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
