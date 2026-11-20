#!/usr/bin/bash
# Write down what's in a SparkOS image, for comparing two builds (build-containerfile.yml).
#   sudo build_files/dump-image.sh IMAGE OUTDIR
# Runs the image with podman (no boot) and writes:
#   packages.txt   every installed package, name-epoch:version-release.arch
#   files.txt      every path under /etc and /usr: type, mode, owner, size, link target
#   sums.txt       sha256 of every regular file under /etc and /usr
#   os-release, policy.json, registries.d.txt, pki.txt, kargs.txt, units.txt, lint.txt
#   image.json     labels, layer count, size on disk; compressed.txt  size in the registry
set -euo pipefail

image=${1:?image}
out=${2:?output folder}
mkdir -p "$out"

podman run --rm --net=none -v "$(readlink -f "$out")":/out "$image" bash -c '
  set -euo pipefail
  rpm -qa --qf "%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n" | sort > /out/packages.txt
  # podman puts its own hosts, hostname and resolv.conf in /etc while the container runs
  skip="/etc/(hosts|hostname|resolv\.conf)"
  tab=$(printf "\t")
  find /etc /usr -xdev -printf "%y %m %u:%g %s %p\t%l\n" | grep -Ev "^[^ ]+ [^ ]+ [^ ]+ [^ ]+ ${skip}${tab}" > /out/files.txt
  find /etc /usr -xdev -type f -print0 | xargs -0 -r sha256sum | grep -Ev "  ${skip}$" > /out/sums.txt
  cp /usr/lib/os-release /out/os-release
  cp /etc/containers/policy.json /out/policy.json
  for f in /etc/containers/registries.d/*.yaml; do echo "--- $f"; cat "$f"; done > /out/registries.d.txt
  ls -l /etc/pki/containers/ > /out/pki.txt
  cat /usr/lib/bootc/kargs.d/*.toml > /out/kargs.txt 2>/dev/null || true
  # Enabled units, from the symlinks systemctl enable makes (systemd is not running here)
  find /etc/systemd /usr/lib/systemd -xdev -path "*.wants/*" -printf "%p -> %l\n" | sort > /out/units.txt
  chmod -R a+rX /out
'

# What bootc itself thinks of the image (BlueBuild doesn't run this; information only)
podman run --rm --net=none "$image" bootc container lint > "$out/lint.txt" 2>&1 || true

podman image inspect "$image" --format '{"labels": {{json .Labels}}, "layers": {{len .RootFS.Layers}}, "size": {{.Size}}}' > "$out/image.json"

# Size in the registry: what a machine downloads for a fresh install
ref=$(podman image inspect "$image" --format '{{index .RepoTags 0}}')
skopeo inspect --raw "docker://$ref" > "$out/manifest.json"
python3 - "$out/manifest.json" "$ref" > "$out/compressed.txt" <<'EOF'
import json, subprocess, sys
m = json.load(open(sys.argv[1])); ref = sys.argv[2]
if "manifests" in m:   # an index (BlueBuild pushes one, with an attestation next to the image)
    d = next(x["digest"] for x in m["manifests"] if (x.get("platform") or {}).get("architecture") == "amd64")
    m = json.loads(subprocess.check_output(["skopeo", "inspect", "--raw", "docker://" + ref.rsplit(":", 1)[0] + "@" + d]))
print(len(m["layers"]), sum(l["size"] for l in m["layers"]))
EOF
echo "dumped $image to $out: $(wc -l < "$out/packages.txt") packages, $(wc -l < "$out/files.txt") paths"
