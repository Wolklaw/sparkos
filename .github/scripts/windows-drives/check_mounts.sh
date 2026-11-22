#!/usr/bin/bash
# Checks what sparkos-windows-drives did with the disk from make_disk.sh: C: and E: read-write with ntfs3, owned by USER, D: read-only,
# and the JSON Nova reads. Runs on the CI runner (as root) and inside the boot-test VM.
#
#   check_mounts.sh USER [STATE_JSON]
set -euo pipefail
user=${1:?user who should own the files}
state=${2:-/run/sparkos/windows-drives.json}
as() { if [ "$(id -un)" = "$user" ]; then bash -c "$1"; else sudo -u "$user" bash -c "$1"; fi; }

echo "--- $state"
cat "$state"
python3 - "$state" <<'EOF'
import json, sys
rows = {r["letter"]: r for r in json.load(open(sys.argv[1]))}
for letter, mode in (("C", "rw"), ("D", "ro"), ("E", "rw")):
    r = rows.get(letter)
    assert r, f"{letter}: missing from the JSON"
    assert r["mountpoint"] == f"/var/mnt/{letter.lower()}", r
    assert r["mode"] == mode, r
    assert set(r) == {"letter", "label", "device", "partuuid", "mountpoint", "mode", "problem"}, r
assert rows["E"]["label"] == "Games" and rows["D"]["label"] == "Scrap"
print("JSON ok")
EOF
for l in c d e; do
  fs=$(findmnt -n -o FSTYPE "/var/mnt/$l")
  [ "$fs" = ntfs3 ] || { echo "/var/mnt/$l is $fs, not ntfs3"; exit 1; }
done
findmnt -n -o OPTIONS /var/mnt/d | grep -q '^ro' || { echo "D: isn't read-only"; exit 1; }
[ "$(stat -c %U /var/mnt/e)" = "$user" ] || { echo "E: belongs to $(stat -c %U /var/mnt/e), not $user"; exit 1; }
as 'touch "/var/mnt/e/Personal Projects/demo/written-on-linux" && rm "/var/mnt/e/Personal Projects/demo/written-on-linux"'
as 'touch /var/mnt/c/Users/Tester/.claude/linux-test && rm /var/mnt/c/Users/Tester/.claude/linux-test'
if as 'touch /var/mnt/d/should-fail' 2>/dev/null; then echo "wrote to D:"; exit 1; fi
test -f /var/mnt/c/Windows/System32/config/SYSTEM
grep -q 'a memory from Windows' /var/mnt/c/Users/Tester/.claude/projects/E--Personal-Projects-demo/memory/MEMORY.md
# Git sees the repository as the user's, and line endings come out as Windows left them with autocrlf
as 'cd "/var/mnt/e/Personal Projects/demo" && git -c core.autocrlf=true -c core.filemode=false status --porcelain | tee /tmp/git-status.txt && test ! -s /tmp/git-status.txt'
echo "Windows drives: all checks passed"
