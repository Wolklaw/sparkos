#!/usr/bin/bash
# Containerfile step 7: the signing policy (the recipe's "signing" step).
#   signing.sh REGISTRY NAME [NAME...]     e.g. signing.sh ghcr.io/wolklaw sparkos sparkos-nvidia
#
# Tells rpm-ostree/bootc to accept updates of each REGISTRY/NAME only when they're signed with
# SparkOS's key (/etc/pki/containers/<first NAME>.pub, copied in step 1), and to look for the
# signature next to the image in the registry (sigstore attachments). Same result as BlueBuild's
# signing module, written in Python instead of jq.
#
# Both SparkOS builds list both images (sparkos and sparkos-nvidia, signed with the same key), so
# a PC can switch from one to the other with a signed rebase.
#
# The registries.d file keeps the name BlueBuild gave it (Wolklaw-sparkos.yaml): machines that
# move from the BlueBuild image to this one then end up with one file, not two with the same entry.
set -euo pipefail

registry=${1:?registry, e.g. ghcr.io/wolklaw}
shift
[ "$#" -ge 1 ] || { echo "give at least one image name, e.g. sparkos"; exit 1; }
key="/etc/pki/containers/${1//\//_}.pub"
policy=/etc/containers/policy.json

test -s "$key" || { echo "missing $key (the Containerfile copies cosign.pub there first)"; exit 1; }
test -f "$policy" || { echo "missing $policy in the base image"; exit 1; }
mkdir -p /etc/containers/registries.d

for name in "$@"; do
image="$registry/$name"
echo "Signing policy for $image (key $key)"

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
# SparkOS's entries last, where BlueBuild's images had theirs
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
done
