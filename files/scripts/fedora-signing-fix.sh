#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). The same fix as sparkos-signing-fix.sh, for the
# prototype's own image name: BlueBuild's signing module writes the policy entry with the
# owner's name as typed ("ghcr.io/Wolklaw/sparkos-fedora"), and container policy matching is
# case-sensitive, so updates would fall through to "insecureAcceptAnything". This renames the
# entry (and the sigstore setting in registries.d) to the lowercase image name.
set -oue pipefail

IMAGE=ghcr.io/wolklaw/sparkos-fedora
POLICY=/etc/containers/policy.json

python3 - "$POLICY" "$IMAGE" <<'PY'
import json, sys
path, image = sys.argv[1], sys.argv[2]
policy = json.load(open(path))
docker = policy["transports"]["docker"]
matches = [k for k in docker if k.lower() == image and k != image]
for k in matches:
    docker[image] = docker.pop(k)
if image not in docker:
    sys.exit(f"no signing policy for {image} in {path}; did the signing module run? keys: {list(docker)}")
entry = docker[image][0]
if entry.get("type") != "sigstoreSigned" or not entry.get("keyPath", "").endswith(".pub"):
    sys.exit(f"unexpected policy for {image}: {entry}")
json.dump(policy, open(path, "w"), indent=2)
print(f"policy: {', '.join(matches) or image} -> {image} ({entry['type']}, {entry['keyPath']})")
PY

for f in /etc/containers/registries.d/*.yaml; do
  grep -qi "ghcr.io/wolklaw/sparkos-fedora" "$f" || continue
  sed -i "s|ghcr.io/[Ww][Oo][Ll][Kk][Ll][Aa][Ww]/sparkos-fedora|$IMAGE|g" "$f"
  echo "--- $f"; cat "$f"
done

# Fail the build if the lowercase entry or its key is missing
grep -q "\"$IMAGE\"" "$POLICY"
KEY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["transports"]["docker"][sys.argv[2]][0]["keyPath"])' "$POLICY" "$IMAGE")
test -s "$KEY"
echo "key: $KEY"
grep -rq "$IMAGE:" /etc/containers/registries.d/

# Install signed. Bazzite does this with /usr/lib/bootc/install/20-bazzite.toml: an installer
# (bootc install, image-builder, Anaconda) then deploys "ostree-image-signed:docker://..." and
# checks the signature, instead of "ostree-unverified-registry:" which never checks it.
mkdir -p /usr/lib/bootc/install
cat > /usr/lib/bootc/install/20-sparkos.toml <<'TOML'
[install]
root-fs-type = "btrfs"
# Deploy as ostree-image-signed, so every update is checked against /etc/pki/containers
enforce-container-sigpolicy = true
TOML
cat /usr/lib/bootc/install/20-sparkos.toml
