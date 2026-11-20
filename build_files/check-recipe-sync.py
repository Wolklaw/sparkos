#!/usr/bin/env python3
"""Check that the Containerfile still builds what recipes/recipe.yml describes.

While both builds exist side by side, the recipe is what everyone edits. This fails (exit 1) and
says what differs when the Containerfile no longer has the same base, the same packages removed
and installed, or the same scripts in the same order, so the side-by-side image can't drift away
from the real one without anyone noticing.

    python3 build_files/check-recipe-sync.py [recipe.yml] [Containerfile]

Needs PyYAML (python3-yaml), which GitHub's Ubuntu runners have.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
recipe_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "recipes" / "recipe.yml"
containerfile_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "Containerfile"

recipe = yaml.safe_load(recipe_path.read_text())
text = containerfile_path.read_text()

# Join continued lines, drop comments: one entry per instruction
instructions = []
current = ""
for line in text.splitlines():
    stripped = line.strip()
    if not current and (not stripped or stripped.startswith("#")):
        continue
    if stripped.startswith("#"):
        continue
    if stripped.endswith("\\"):
        current += stripped[:-1] + " "
        continue
    instructions.append(current + stripped)
    current = ""


def words_after(command, marker, stop=("&&",)):
    """The words after marker in command, up to the next stop word."""
    words = command.split()
    for i in range(len(words) - len(marker) + 1):
        if words[i:i + len(marker)] == marker:
            out = []
            for w in words[i + len(marker):]:
                if w in stop:
                    break
                out.append(w)
            return out
    return None


problems = []

# Base image
want_base = f"{recipe['base-image']}:{recipe['image-version']}"
m = re.search(r"^ARG BASE_IMAGE=(\S+)", text, re.M)
if not m or m.group(1) != want_base:
    problems.append(f"base image: recipe has {want_base}, Containerfile has {m.group(1) if m else 'none'}")

# What the Containerfile does, in order
cf_steps = []
for ins in instructions:
    if not ins.startswith("RUN "):
        continue
    if "copy-files.sh" in ins:
        src, dest = words_after(ins, ["/tmp/build_files/copy-files.sh"])[:2]
        cf_steps.append(("files", [(src, dest)]))
    elif "dnf -y remove" in ins or "install_weak_deps" in ins:
        remove = words_after(ins, ["dnf", "-y", "remove"]) or []
        install = words_after(ins, ["dnf", "-y", "--setopt=install_weak_deps=True", "install"]) or []
        cf_steps.append(("dnf", (sorted(install), sorted(remove))))
    elif "run-scripts.sh" in ins:
        cf_steps.append(("script", words_after(ins, ["/tmp/build_files/run-scripts.sh"])))
    elif "flathub.sh" in ins:
        cf_steps.append(("default-flatpaks", ["system", "user"]))
    elif "signing.sh" in ins:
        cf_steps.append(("signing", None))

# What the recipe asks for, in order
recipe_steps = []
for module in recipe["modules"]:
    kind = module["type"].split("@")[0]
    if kind == "files":
        recipe_steps.append(("files", [(f["source"], f["destination"]) for f in module["files"]]))
    elif kind == "dnf":
        install = [p for p in module.get("install", {}).get("packages", []) if isinstance(p, str)]
        remove = list(module.get("remove", {}).get("packages", []))
        extra = set(module) - {"type", "install", "remove", "source"}
        extra |= set(module.get("install", {})) - {"packages"}
        extra |= set(module.get("remove", {})) - {"packages"}
        if extra or len(install) != len(module.get("install", {}).get("packages", [])):
            problems.append(f"dnf step uses options the Containerfile doesn't handle yet: {sorted(extra) or 'repo-specific packages'}")
        recipe_steps.append(("dnf", (sorted(install), sorted(remove))))
    elif kind == "script":
        if module.get("snippets"):
            problems.append("script step has snippets; the Containerfile only runs scripts")
        recipe_steps.append(("script", list(module.get("scripts", []))))
    elif kind == "default-flatpaks":
        confs = module.get("configurations", [])
        if any(c.get("install") for c in confs):
            problems.append("default-flatpaks installs apps now; flathub.sh only adds the remote")
        if any(c.get("repo") for c in confs):
            problems.append("default-flatpaks uses another repo than Flathub; flathub.sh doesn't")
        recipe_steps.append(("default-flatpaks", sorted(c.get("scope", "user") for c in confs)))
    elif kind == "signing":
        recipe_steps.append(("signing", None))
    else:
        problems.append(f"recipe has a '{kind}' step the Containerfile doesn't do")
        recipe_steps.append((kind, None))

if [s[0] for s in cf_steps] != [s[0] for s in recipe_steps]:
    problems.append(f"step order: recipe {[s[0] for s in recipe_steps]}, Containerfile {[s[0] for s in cf_steps]}")
else:
    for (kind, want), (_, have) in zip(recipe_steps, cf_steps):
        if kind == "dnf":
            for label, w, h in (("install", want[0], have[0]), ("remove", want[1], have[1])):
                if w != h:
                    missing, extra = sorted(set(w) - set(h)), sorted(set(h) - set(w))
                    problems.append(f"dnf {label}: missing in Containerfile {missing}, not in recipe {extra}")
        elif want != have:
            problems.append(f"{kind} step: recipe {want}, Containerfile {have}")

if problems:
    print("The Containerfile no longer matches recipes/recipe.yml:")
    for p in problems:
        print(f"  - {p}")
    print("Update the Containerfile to match (docs/building.md says how each step maps).")
    sys.exit(1)
print(f"Containerfile matches {recipe_path.name}: {len(recipe_steps)} steps, same packages and scripts in the same order.")
