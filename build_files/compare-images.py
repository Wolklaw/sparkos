#!/usr/bin/env python3
"""Compare two dumps made by dump-image.sh and write a Markdown report.

    python3 build_files/compare-images.py BLUEBUILD_DIR CONTAINERFILE_DIR > report.md

Lists every difference: packages, paths that exist in only one image, changed modes or owners,
files whose contents differ (grouped by folder), os-release, signing policy, enabled units,
labels and size. Exit code 0 even when they differ: explaining the differences is a person's job.
"""
import json
import sys
from collections import Counter
from pathlib import Path

A, B = Path(sys.argv[1]), Path(sys.argv[2])
NAMES = ("BlueBuild", "Containerfile")
LIMIT = 200  # lines per list in the report; the full lists are in the uploaded files


def lines(p):
    return p.read_text(errors="replace").splitlines() if p.exists() else []


def files(d):
    out = {}
    for line in lines(d / "files.txt"):
        meta, _, target = line.partition("\t")
        kind, mode, owner, size, path = meta.split(" ", 4)
        out[path] = (kind, mode, owner, int(size), target)
    return out


def sums(d):
    out = {}
    for line in lines(d / "sums.txt"):
        digest, _, path = line.partition("  ")
        out[path] = digest
    return out


def block(title, items, empty="none"):
    items = list(items)
    print(f"\n#### {title} ({len(items)})\n")
    if not items:
        print(empty)
        return
    print("```")
    for i in items[:LIMIT]:
        print(i)
    if len(items) > LIMIT:
        print(f"... and {len(items) - LIMIT} more (see the uploaded comparison files)")
    print("```")


def folder(path, depth=3):
    return "/".join(path.split("/")[: depth + 1])


def human(n):
    return f"{n / 1e9:.2f} GB"


print(f"## {NAMES[0]} image vs {NAMES[1]} image\n")

# Images: labels, layers, sizes
ia, ib = (json.loads((d / "image.json").read_text()) for d in (A, B))
ca, cb = ((lines(d / "compressed.txt") or ["0 0"])[0].split() for d in (A, B))
print("| | " + " | ".join(NAMES) + " |\n|---|---|---|")
print(f"| Size on disk | {human(ia['size'])} | {human(ib['size'])} |")
print(f"| Download (compressed) | {human(int(ca[1]))} in {ca[0]} layers | {human(int(cb[1]))} in {cb[0]} layers |")
pa, pb = lines(A / "packages.txt"), lines(B / "packages.txt")
fa, fb = files(A), files(B)
print(f"| Packages | {len(pa)} | {len(pb)} |")
print(f"| Paths in /etc and /usr | {len(fa)} | {len(fb)} |")
la, lb = ia.get("labels") or {}, ib.get("labels") or {}
for key in ("org.opencontainers.image.base.digest", "org.opencontainers.image.version"):
    print(f"| {key.split('.')[-2] + '.' + key.split('.')[-1]} | `{la.get(key, '')}` | `{lb.get(key, '')}` |")

block("Packages only in the BlueBuild image", sorted(set(pa) - set(pb)))
block("Packages only in the Containerfile image", sorted(set(pb) - set(pa)))

only_a = sorted(set(fa) - set(fb))
only_b = sorted(set(fb) - set(fa))
fmt = lambda p, d: f"{d[p][0]} {d[p][1]} {d[p][2]} {p}" + (f" -> {d[p][4]}" if d[p][4] else "")
block("Paths only in the BlueBuild image", [fmt(p, fa) for p in only_a])
block("Paths only in the Containerfile image", [fmt(p, fb) for p in only_b])

meta = []
for p in sorted(set(fa) & set(fb)):
    a, b = fa[p], fb[p]
    if a[0] != b[0] or a[1] != b[1] or a[2] != b[2] or a[4] != b[4]:
        meta.append(f"{p}: {a[0]} {a[1]} {a[2]} {a[4]} | {b[0]} {b[1]} {b[2]} {b[4]}")
block("Same path, different type, mode, owner or link target (BlueBuild | Containerfile)", meta)

sa, sb = sums(A), sums(B)
changed = sorted(p for p in set(sa) & set(sb) if sa[p] != sb[p])
by_folder = Counter(folder(p) for p in changed)
block("Files with different contents, by folder", [f"{n:6d}  {f}" for f, n in by_folder.most_common()])
block("Files with different contents under /etc", [p for p in changed if p.startswith("/etc/")])
block("Files with different contents (all)", changed)

for name in ("os-release", "policy.json", "registries.d.txt", "pki.txt", "kargs.txt", "units.txt"):
    xa, xb = lines(A / name), lines(B / name)
    if xa == xb:
        print(f"\n#### {name}: identical\n")
    else:
        import difflib
        diff = list(difflib.unified_diff(xa, xb, NAMES[0], NAMES[1], lineterm="", n=1))
        block(f"{name}: differs", diff)

lkeys = sorted(set(la) | set(lb))
block("Labels that differ (BlueBuild | Containerfile)",
      [f"{k}: {la.get(k, '-')} | {lb.get(k, '-')}" for k in lkeys if la.get(k) != lb.get(k)])
