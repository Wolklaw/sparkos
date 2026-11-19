#!/usr/bin/env bash
# Make SparkOS updates actually verify their signature.
#
# BlueBuild's signing module names the policy entry after the GitHub owner as written
# ("ghcr.io/Wolklaw/sparkos"). Image names are always lowercase and container policy
# matching is case-sensitive, so that entry never applied: updates fell through to the
# catch-all "insecureAcceptAnything" rule. This renames the entry (and the matching
# sigstore setting in registries.d) to the lowercase image name. Runs after the signing module.
set -oue pipefail

IMAGE=ghcr.io/wolklaw/sparkos
POLICY=/etc/containers/policy.json

python3 - "$POLICY" "$IMAGE" <<'EOF'
import json, sys
path, image = sys.argv[1], sys.argv[2]
policy = json.load(open(path))
docker = policy["transports"]["docker"]
matches = [k for k in docker if k.lower() == image and k != image]
for k in matches:
    docker[image] = docker.pop(k)
if image not in docker:
    sys.exit(f"no signing policy for {image} in {path}; did the signing module run?")
entry = docker[image][0]
if entry.get("type") != "sigstoreSigned" or not entry.get("keyPath", "").endswith("sparkos.pub"):
    sys.exit(f"unexpected policy for {image}: {entry}")
json.dump(policy, open(path, "w"), indent=2)
print(f"policy: {', '.join(matches) or image} -> {image} ({entry['type']}, {entry['keyPath']})")
EOF

for f in /etc/containers/registries.d/*.yaml; do
  grep -qi "ghcr.io/wolklaw/sparkos" "$f" || continue
  sed -i "s|ghcr.io/[Ww][Oo][Ll][Kk][Ll][Aa][Ww]/sparkos|$IMAGE|g" "$f"
  echo "--- $f"; cat "$f"
done

# Fail the build if the lowercase entry or the key is missing
grep -q "\"$IMAGE\"" "$POLICY"
test -s /etc/pki/containers/sparkos.pub
grep -rq "$IMAGE:" /etc/containers/registries.d/
