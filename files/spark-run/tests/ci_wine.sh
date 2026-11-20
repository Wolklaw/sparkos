#!/usr/bin/env bash
# Spark Run on real Wine, the way CI runs it (the Fedora container, and as a normal user inside
# the SparkOS image). Downloads the pinned Wine and Wine Mono for real (checked against their
# SHA-256), then runs and installs the test programs from tests/fixtures/build.sh.
#
#   tests/ci_wine.sh FIXTURES_DIR [SPARK_RUN_COMMAND]
#
# Writes timings and sizes to $GITHUB_STEP_SUMMARY when it's set.
set -euo pipefail
fx=$(cd "${1:?folder with the built test programs}" && pwd)
SR=${2:-spark-run}
out=$(mktemp -d)
summary=${GITHUB_STEP_SUMMARY:-/dev/null}
data=${XDG_DATA_HOME:-$HOME/.local/share}/spark-run
apps=${XDG_DATA_HOME:-$HOME/.local/share}/applications
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }
got() { tr -d '\r' < "$1"; }      # what Spark Hello wrote, without Windows line endings
winpath() { printf 'Z:%s' "$(printf '%s' "$1" | tr / '\\')"; }
t0=$(date +%s)
since() { echo $(( $(date +%s) - $1 )); }
row() { echo "| $1 | $2 |" >> "$summary"; }

echo "--- $($SR --version), display: ${DISPLAY:-none}, user: $(id -un)"
{ echo "### Spark Run on real Wine ($(id -un), display ${DISPLAY:-none})"; echo
  echo "| step | result |"; echo "|---|---|"; } >> "$summary"

echo "--- setup: download Wine and Wine Mono, check their SHA-256, unpack"
t=$(date +%s)
$SR --setup
row "download + check + unpack Wine and Wine Mono" "$(since "$t") s"
wine_dir=$(ls -d "$data"/runtime/wine-*/ | head -1)
row "Wine on disk (with Wine Mono)" "$(du -sh "$wine_dir" | cut -f1)"
[ -d "$wine_dir/share/wine/mono/wine-mono-11.3.0" ] || fail "Wine Mono not unpacked"
test -z "$(ls -A "${XDG_CACHE_HOME:-$HOME/.cache}/spark-run" 2>/dev/null | grep -v '^font$')" \
  || fail "downloads left in the cache"
pass "Wine downloaded and verified"

report=$($SR --self-test) || { echo "$report"; fail "self-test"; }
echo "$report"
grep -q '^wine says: wine-11.22' <<<"$report" || fail "self-test didn't run wine"
pass "self-test with Wine"

echo "--- run once: 64-bit, then 32-bit (the first one makes the run-once prefix)"
export SPARK_HELLO_OUT; SPARK_HELLO_OUT=$(winpath "$out/once.txt")
t=$(date +%s)
$SR --run-once "$fx/hello64.exe" "first arg" second --wait --no-window
row "run once, 64-bit (makes the run-once prefix)" "$(since "$t") s"
t=$(date +%s)
$SR --run-once "$fx/hello32.exe" --wait --no-window
row "run once, 32-bit (prefix already there)" "$(since "$t") s"
cat "$out/once.txt"
got "$out/once.txt" | grep -q \
  '^hello from Spark Hello, 64-bit, Windows 10.0, args: \[first arg\] \[second\]$' \
  || fail "64-bit run once"
got "$out/once.txt" | grep -q '^hello from Spark Hello, 32-bit, Windows 10.0, args:$' \
  || fail "32-bit run once (wow64)"
pass "run once, 64 and 32-bit"
row "run-once prefix on disk" "$(du -sh --one-file-system "$data/run-once" | cut -f1)"

echo "--- a plain error, not Wine's output"
set +e
err=$($SR --run-once "$fx/needs-missing-dll.exe" --wait --no-window 2>&1 >/dev/null)
code=$?
set -e
echo "$err"
[ "$code" = 1 ] || fail "missing DLL: exit code $code"
grep -q 'needs sparkmissing.dll' <<<"$err" || fail "missing DLL not explained"
grep -q 'switching.md' <<<"$err" || fail "no link to the switching guide"
! grep -q 'Traceback\|err:module' <<<"$err" || fail "raw output shown"
pass "missing DLL explained in one sentence"

echo "--- install the NSIS installer as an app"
t=$(date +%s)
$SR --install "$fx/spark-hello-setup.exe" --no-window | tee "$out/nsis.json"
row "install (NSIS installer, new prefix)" "$(since "$t") s"
python3 - "$out/nsis.json" <<'PY'
import json, sys
text = open(sys.argv[1]).read()
app = json.loads(text[text.index('{'):])
assert app['slug'] == 'spark-hello', app
assert app['name'] == 'Spark Hello', app
assert app['program'] == 'C:\\Program Files\\Spark Hello\\Spark Hello.exe', app
assert [c['name'] for c in app['candidates']] == ['Spark Hello'], app   # not the uninstaller
assert app['wm_class'] == 'spark hello.exe', app
PY
entry="$apps/dev.wolklaw.SparkRun.app-spark-hello.desktop"
cat "$entry"
grep -q '^Name=Spark Hello$' "$entry" || fail "menu entry name"
grep -q -- '--open spark-hello %F$' "$entry" || fail "menu entry Exec"
icon=$(sed -n 's/^Icon=//p' "$entry")
[ "$icon" = "$data/prefixes/spark-hello/icon.png" ] || fail "menu entry icon: $icon"
python3 -c "
from PIL import Image; im = Image.open('$icon'); print('icon', im.size, im.mode)
assert im.size == (256, 256), im.size" || fail "icon read from the .exe"
command -v desktop-file-validate >/dev/null && desktop-file-validate "$entry"
pass "installed with its menu entry and its own icon"
row "app prefix on disk" "$(du -sh --one-file-system "$data/prefixes/spark-hello" | cut -f1)"

echo "--- open it from the menu entry's command, with a file"
SPARK_HELLO_OUT=$(winpath "$out/app.txt")
touch "$out/doc one.txt"
t=$(date +%s)
$SR --open spark-hello "$out/doc one.txt" --wait --no-window
row "open the installed app" "$(since "$t") s"
cat "$out/app.txt"
got "$out/app.txt" | grep -qF "64-bit, Windows 10.0, args: [$(winpath "$out/doc one.txt")]" \
  || fail "open with a file"
pass "opens, with the file as a Windows path"

echo "--- options: Windows 7, then DXVK (downloaded and checked)"
$SR --set spark-hello --windows win7 >/dev/null
$SR --open spark-hello --wait --no-window
got "$out/app.txt" | grep -q 'Windows 6.1, args:$' || fail "Windows version 7"
t=$(date +%s)
$SR --set spark-hello --dxvk on >/dev/null
row "DXVK on (download + check)" "$(since "$t") s"
for f in system32/d3d11.dll system32/dxgi.dll syswow64/d3d11.dll; do
  test -f "$data/prefixes/spark-hello/drive_c/windows/$f" || fail "DXVK $f"
done
$SR --open spark-hello --wait --no-window
pass "Windows version and DXVK options"

echo "--- install an .msi (no shortcut: found by its new .exe)"
SPARK_HELLO_OUT=$(winpath "$out/msi.txt")
t=$(date +%s)
$SR --install "$fx/spark-hello-msi.msi" --silent --no-window | tee "$out/msi.json"
row "install (.msi, silent)" "$(since "$t") s"
python3 - "$out/msi.json" <<'PY' || fail ".msi program"
import json, sys
text = open(sys.argv[1]).read()
app = json.loads(text[text.index('{'):])
print(app['slug'], app['program'])
assert app['slug'] == 'spark-hello-msi', app
assert app['program'].endswith('\\Spark Hello MSI\\SparkHelloMsi.exe'), app
PY
$SR --open spark-hello-msi --wait --no-window
grep -q '32-bit' "$out/msi.txt" || fail ".msi app runs"
pass ".msi installed and opens"

echo "--- install a program that needs no installer"
SPARK_HELLO_OUT=$(winpath "$out/portable.txt")
$SR --install "$fx/hello64.exe" --name "Hello Portable" --no-window | tee "$out/portable.json"
grep -q '"name": "Hello Portable"' "$out/portable.json" || fail "portable name"
slug=$(python3 -c "import json,sys; t=open('$out/portable.json').read(); print(json.loads(t[t.index('{'):])['slug'])")
$SR --open "$slug" --wait --no-window
grep -q '64-bit' "$out/portable.txt" || fail "portable app runs"
pass "program copied in and opens"

echo "--- list and uninstall"
$SR --list
[ "$($SR --list | wc -l)" = 3 ] || fail "three apps listed"
for s in spark-hello spark-hello-msi "$slug"; do $SR --uninstall "$s" --quiet; done
[ -z "$(ls -A "$data/prefixes")" ] || fail "prefixes left: $(ls "$data/prefixes")"
! ls "$apps"/dev.wolklaw.SparkRun.app-* >/dev/null 2>&1 || fail "menu entries left"
pass "uninstalled; prefixes and menu entries gone"

row "total" "$(since "$t0") s"
rm -rf "$out"
echo "all real-Wine checks passed"
