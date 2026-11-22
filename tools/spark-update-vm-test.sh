#!/usr/bin/env bash
# Spark Update in a real VM: a SparkOS system updates itself to a newer image, restarts into it,
# rolls back, doesn't take the same image again, and takes the next newer one.
#
#   tools/spark-update-vm-test.sh [image]      (default ghcr.io/wolklaw/sparkos-fedora:latest)
#
# Rootless: needs podman and /dev/kvm, no sudo, nothing installed on the host. QEMU runs in a
# Fedora container. From the image it builds three test images (this checkout's Spark Update
# copied in; a marker file /usr/share/sparkos-update-test saying old, new, newer; versions
# .90/.91/.92) and serves them from a local registry (registry:2 on 127.0.0.1). A helper VM
# (Fedora Cloud) installs "old" on a disk with `bootc install to-disk`, following the local
# registry; then the SparkOS VM boots that disk and Spark Update does the rest the way its
# timer does (systemctl start spark-update.service).
#
# The local registry is plain HTTP and unsigned, so signature checking of updates is NOT
# tested here (the VM accepts any image from it). The disk boots with BIOS (the helper VM
# installs from BIOS); the update path doesn't depend on the firmware.
#
# Everything lives in $WORK (default /var/tmp/spark-update-vm-test, about 25 GB while it
# runs) and is removed at the end, with the containers and test images, unless KEEP=1.
# Ports: REG_PORT (5055) and SSH_PORT (2245) on 127.0.0.1. Takes about 15 minutes.
set -euo pipefail

BASE=${1:-ghcr.io/wolklaw/sparkos-fedora:latest}
WORK=${WORK:-/var/tmp/spark-update-vm-test}
REG_PORT=${REG_PORT:-5055}
SSH_PORT=${SSH_PORT:-2245}
REPO=$(cd "$(dirname "$0")/.." && pwd)
NAME=$(basename "${BASE%%[:@]*}")              # sparkos-fedora: Spark Update knows the name
REG=localhost:$REG_PORT/$NAME                  # as the host sees it
VMREG=10.0.2.2:$REG_PORT/$NAME                 # as the VMs see it (QEMU user network)
TOOLS=localhost/spark-update-vm-test-tools
CLOUD=https://download.fedoraproject.org/pub/fedora/linux/releases/45/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-45-1.4.x86_64.qcow2
PFX=sut-$$

T0=$(date +%s)
step() { echo; echo "=== [$(( $(date +%s) - T0 ))s] $*"; }
fail() { echo "FAILED: $*"; exit 1; }
build() {      # podman build, its output only on failure
  podman build -t "$@" >"$WORK/build.log" 2>&1 || { tail -30 "$WORK/build.log"; fail "podman build $1"; }
}
vm() { ssh -i "$WORK/id" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
         -o ConnectTimeout=5 -o LogLevel=ERROR -p "$SSH_PORT" root@127.0.0.1 "$@"; }
wait_ssh() {
  local s=$(date +%s)
  for _ in $(seq 1 150); do
    if vm true 2>/dev/null; then echo "SSH answers after $(( $(date +%s) - s ))s"; return 0; fi
    sleep 2
  done
  tail -40 "$WORK/serial.log" 2>/dev/null; fail "no SSH"
}
qemu() {       # qemu <name> <args...>: QEMU in the tools container, in the background
  local name=$1; shift
  podman run -d --name "$name" --network host --device /dev/kvm --security-opt label=disable \
    -v "$WORK:/work" "$TOOLS" qemu-system-x86_64 -enable-kvm -cpu host -machine q35 -m 8192 \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22 -display none "$@" >/dev/null
}
reboot_vm() {
  vm 'systemctl reboot' || true
  sleep 5
  wait_ssh
}
marker() { vm 'cat /usr/share/sparkos-update-test'; }
due_run() {    # what spark-update.timer starts, with the next check due
  vm 'python3 -c "
import json, os; p=\"/var/lib/spark-update/state.json\"; os.makedirs(os.path.dirname(p), exist_ok=True)
try: d=json.load(open(p))
except OSError: d={}
d[\"last_check\"]=d.get(\"last_check\", 0)-7*3600; json.dump(d, open(p, \"w\"))"
      s=$(date +%s); systemctl start spark-update.service; echo "spark-update.service: exit $? in $(( $(date +%s) - s ))s"
      python3 -c "import json; d=json.load(open(\"/var/lib/spark-update/state.json\")); print(\"state:\", {k: d.get(k) for k in (\"result\", \"staged_version\", \"error\", \"held\")})"'
}
cleanup() {
  [ "${KEEP:-0}" = 1 ] && { echo "KEEP=1: left $WORK and the containers"; return; }
  podman rm -f "$PFX-helper" "$PFX-vm" "$PFX-registry" >/dev/null 2>&1 || true
  podman rmi -f "$REG:old" "$REG:new" "$REG:newer" "$TOOLS" >/dev/null 2>&1 || true
  podman unshare rm -rf "$WORK" 2>/dev/null || rm -rf "$WORK"
}
trap cleanup EXIT

[ -w /dev/kvm ] || fail "/dev/kvm isn't usable"
mkdir -p "$WORK/registry"

step "Tools: QEMU in a Fedora container; registry:2 on 127.0.0.1:$REG_PORT"
printf 'FROM registry.fedoraproject.org/fedora:45\nRUN dnf -y install qemu-system-x86-core qemu-img openssh-clients cloud-utils xorriso && dnf clean all\n' \
  > "$WORK/Containerfile.tools"
build "$TOOLS" -f "$WORK/Containerfile.tools" "$WORK"
podman run -d --name "$PFX-registry" -p "127.0.0.1:$REG_PORT:5000" --security-opt label=disable \
  -v "$WORK/registry:/var/lib/registry" docker.io/library/registry:2 >/dev/null

step "Test images from $BASE"
podman image exists "$BASE" || podman pull -q "$BASE" >/dev/null
cat > "$WORK/Containerfile.old" <<EOF
FROM $BASE
COPY sparkupdate/*.py /usr/lib/spark-update/sparkupdate/
COPY spark_update.py /usr/lib/spark-update/
COPY systemd/spark-update.service systemd/spark-update.timer systemd/spark-update-now@.service /usr/lib/systemd/system/
RUN rm -rf /usr/lib/spark-update/sparkupdate/__pycache__ && echo old > /usr/share/sparkos-update-test
LABEL org.opencontainers.image.version="45.$(date +%Y%m%d).90"
EOF
build "$REG:old" -f "$WORK/Containerfile.old" "$REPO/files/spark-update"
for v in new:91 newer:92; do
  printf 'FROM %s\nRUN echo %s > /usr/share/sparkos-update-test\nLABEL org.opencontainers.image.version="45.%s.%s"\n' \
    "$REG:old" "${v%%:*}" "$(date +%Y%m%d)" "${v##*:}" > "$WORK/Containerfile.${v%%:*}"
  build "$REG:${v%%:*}" -f "$WORK/Containerfile.${v%%:*}" "$WORK"
done
s=$(date +%s)
podman push -q --tls-verify=false "$REG:old" "$REG:latest"
echo "old pushed as latest in $(( $(date +%s) - s ))s"

step "Install old on a disk (helper VM: Fedora Cloud, bootc install to-disk)"
[ -f "$WORK/cloud.qcow2" ] || curl -sfL -o "$WORK/cloud.qcow2" "$CLOUD"
ssh-keygen -q -t ed25519 -N "" -C spark-update-vm-test -f "$WORK/id"
printf '#cloud-config\ndisable_root: false\nusers:\n  - name: root\n    ssh_authorized_keys:\n      - %s\n' "$(cat "$WORK/id.pub")" > "$WORK/user-data"
printf 'instance-id: helper\nlocal-hostname: helper\n' > "$WORK/meta-data"
podman run --rm --security-opt label=disable -v "$WORK:/work" "$TOOLS" sh -c \
  'cd /work && cloud-localds seed.iso user-data meta-data && qemu-img create -q -f qcow2 -F qcow2 -b cloud.qcow2 helper.qcow2 40G && qemu-img create -q -f qcow2 sparkos.qcow2 40G'
qemu "$PFX-helper" -smp 8 -drive file=/work/helper.qcow2,if=virtio,format=qcow2 \
  -drive file=/work/sparkos.qcow2,if=virtio,format=qcow2 \
  -drive file=/work/seed.iso,if=virtio,format=raw,readonly=on -serial file:/work/helper-serial.log
wait_ssh
vm "dnf -y -q install podman >/dev/null 2>&1
    printf '[[registry]]\nlocation = \"10.0.2.2:$REG_PORT\"\ninsecure = true\n' > /etc/containers/registries.conf.d/50-test.conf
    s=\$(date +%s); podman pull -q $VMREG:latest >/dev/null && echo \"pulled in \$(( \$(date +%s) - s ))s\""
scp -q -i "$WORK/id" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
  -P "$SSH_PORT" "$WORK/id.pub" root@127.0.0.1:/root/key.pub
out=$(vm "s=\$(date +%s)
    podman run --rm --privileged --pid=host -v /var/lib/containers:/var/lib/containers -v /dev:/dev \
      -v /root/key.pub:/key.pub:ro --security-opt label=type:unconfined_t $VMREG:latest \
      bootc install to-disk --wipe --filesystem btrfs --target-imgref $VMREG:latest \
      --root-ssh-authorized-keys /key.pub --karg systemd.wants=sshd.service --karg console=ttyS0,115200 \
      /dev/vdb >/root/install.log 2>&1 || { tail -30 /root/install.log; exit 1; }
    echo \"installed in \$(( \$(date +%s) - s ))s\"; poweroff") || true
echo "$out"
grep -q "^installed in" <<<"$out" || fail "bootc install to-disk failed"
sleep 5
podman rm -f "$PFX-helper" >/dev/null
rm -f "$WORK/helper.qcow2"

step "Boot SparkOS (old)"
qemu "$PFX-vm" -smp 4 -vga std -drive file=/work/sparkos.qcow2,if=virtio,format=qcow2 -serial file:/work/serial.log
wait_ssh
[ "$(marker)" = old ] || fail "not booted into old"
vm "printf '[[registry]]\nlocation = \"10.0.2.2:$REG_PORT\"\ninsecure = true\n' > /etc/containers/registries.conf.d/50-test.conf
    systemctl is-enabled spark-update.timer; spark-update --status"

step "new (.91) in the registry; Spark Update's timer run stages it"
podman push -q --tls-verify=false "$REG:new" "$REG:latest"
out=$(due_run); echo "$out"
grep -q "'result': 'staged'.*'staged_version': '45\.[0-9]*\.91'" <<<"$out" || fail "new not staged"
vm 'spark-update --status'

step "Restart into the update"
reboot_vm
[ "$(marker)" = new ] || fail "the restart didn't start new"
vm 'spark-update --status'

step "Roll back (spark-update --rollback, the window's Roll back) and restart"
vm 'spark-update --rollback 2>&1 | tail -1; spark-update --status'
reboot_vm
[ "$(marker)" = old ] || fail "the restart after roll back didn't start old"

step "Next timer run: the version rolled back from isn't staged again"
out=$(due_run); echo "$out"
grep -q "'result': 'up_to_date'" <<<"$out" && grep -q "'held': {" <<<"$out" || fail "new staged again"
vm 'spark-update --status; bootc status --format json | python3 -c "import json,sys; s=json.load(sys.stdin)[\"status\"]; sys.exit(1 if s.get(\"staged\") else 0)"' \
  || fail "something is staged"

step "newer (.92) in the registry; the timer run stages it and the restart starts it"
podman push -q --tls-verify=false "$REG:newer" "$REG:latest"
out=$(due_run); echo "$out"
grep -q "'result': 'staged'.*'staged_version': '45\.[0-9]*\.92'" <<<"$out" || fail "newer not staged"
reboot_vm
[ "$(marker)" = newer ] || fail "the restart didn't start newer"
vm 'spark-update --status; systemd-analyze | head -1'

step "PASSED in $(( $(date +%s) - T0 ))s"
