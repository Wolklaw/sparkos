#!/usr/bin/bash
# Containerfile step 7: the signing policy.
#   signing.sh REGISTRY IMAGE_NAME     e.g. signing.sh ghcr.io/wolklaw sparkos
#
# Tells rpm-ostree/bootc to accept updates of REGISTRY/IMAGE_NAME only when they're signed with
# SparkOS's key (/etc/pki/containers/IMAGE_NAME.pub, copied in step 1), and to look for the
# signature next to the image in the registry (sigstore attachments). Same result as BlueBuild's
# signing module, written in Python instead of jq.
#
# The registries.d file keeps the name BlueBuild gave it (Wolklaw-sparkos.yaml): machines that
# move from the BlueBuild image to this one then end up with one file, not two with the same entry.
set -euo pipefail

registry=${1:?registry, e.g. ghcr.io/wolklaw}
name=${2:?image name, e.g. sparkos}
image="$registry/$name"
key="/etc/pki/containers/${name//\//_}.pub"
policy=/etc/containers/policy.json

echo "Signing policy for $image (key $key)"
test -s "$key" || { echo "missing $key (the Containerfile copies cosign.pub there first)"; exit 1; }
test -f "$policy" || { echo "missing $policy in the base image"; exit 1; }
mkdir -p /etc/containers/registries.d

python3 - "$policy" "$image" "$key" <<'EOF'
import json, sys
path, image, key = sys.argv[1:4]
policy = json.load(open(path))
# The base image's default must be "reject", or a signature check would mean nothing.
default = policy.get("default", [{}])[0].get("type")
if default != "reject":
    sys.exit(f"{path}: default is {default!r}, expected 'reject'; tell the owner (Bazzite changed its policy)")
entry = [{"type": "sigstoreSigned", "keyPath": key, "signedIdentity": {"type": "matchRepository"}}]
docker = policy.setdefault("transports", {}).get("docker", {})
# SparkOS's entry last, where BlueBuild's images had it (so policy.json on machines installed
# from them doesn't change order on their first update)
policy["transports"]["docker"] = {**{k: v for k, v in docker.items() if k != image}, image: entry}
with open(path, "w") as f:
    json.dump(policy, f, indent=2)
    f.write("\n")
print(f"policy: {image} -> sigstoreSigned, {key}")
EOF

cat > "/etc/containers/registries.d/Wolklaw-${name//\//_}.yaml" <<EOF
docker:
  $image:
    use-sigstore-attachments: true
EOF
cat "/etc/containers/registries.d/Wolklaw-${name//\//_}.yaml"

# Install signed: an installer (bootc install, image-builder, Anaconda) then deploys
# "ostree-image-signed:docker://..." and checks the signature, instead of
# "ostree-unverified-registry:", which never checks it. Bazzite already sets this in
# /usr/lib/bootc/install/20-bazzite.toml; plain Fedora Kinoite doesn't, so SparkOS adds its own.
if grep -qs '^enforce-container-sigpolicy *= *true' /usr/lib/bootc/install/*.toml; then
  echo "bootc install: the base already enforces the signing policy"
else
  mkdir -p /usr/lib/bootc/install
  cat > /usr/lib/bootc/install/20-sparkos.toml <<'TOML'
[install]
root-fs-type = "btrfs"
# Deploy as ostree-image-signed, so every update is checked against /etc/pki/containers
enforce-container-sigpolicy = true
TOML
  cat /usr/lib/bootc/install/20-sparkos.toml
fi
