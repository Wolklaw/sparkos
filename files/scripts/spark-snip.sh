#!/usr/bin/env bash
# Spark Snip, the SparkOS tool for screenshots, copying text off the screen (OCR) and
# screen recording. Its source lives in this repo at files/spark-snip.
#
# It becomes the default for the screenshot keys: Print and Meta+Shift+S take a screenshot,
# Meta+Shift+T copies text, Meta+Shift+R starts and stops a recording. Spark Snip reads the
# screen through KWin itself (the boot test proves it in a real Plasma session), so Spectacle
# is removed in the recipe. If Spectacle is ever back in the image, it gives up those keys.
# Its other shortcuts (Meta+Print and so on) are untouched.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-snip"
test -f "$SRC/install.sh" || { echo "Spark Snip source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

# Hand Print and Meta+Shift+R over from Spectacle to Spark Snip. Defaults only: a user who
# already set their own shortcuts keeps them.
python3 - <<'EOF'
import os

TAKEN = {"Print", "Meta+Shift+R", "Meta+Shift+S", "Meta+Shift+T"}
for path in ("/usr/share/applications/org.kde.spectacle.desktop",
             "/usr/share/kglobalaccel/org.kde.spectacle.desktop"):
    if not os.path.isfile(path) or os.path.islink(path):
        continue
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    for line in lines:
        if line.startswith("X-KDE-Shortcuts="):
            keys = [k for k in line.strip().split("=", 1)[1].split(",") if k and k not in TAKEN]
            line = "X-KDE-Shortcuts=" + ",".join(keys) + "\n"
        out.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
    print(f"--- shortcuts left to Spectacle in {path}:")
    print("".join(l for l in out if l.startswith(("[", "X-KDE-Shortcuts="))))
EOF

# Fail the build if anything is missing, so a broken Spark Snip never ships.
test -x /usr/bin/spark-snip
test -f /usr/share/applications/dev.wolklaw.SparkSnip.desktop
test -L /usr/share/kglobalaccel/dev.wolklaw.SparkSnip.desktop
grep -q '^X-KDE-Shortcuts=Print,Meta+Shift+S$' /usr/share/applications/dev.wolklaw.SparkSnip.desktop
if [ -f /usr/share/applications/org.kde.spectacle.desktop ] && grep -E '^X-KDE-Shortcuts=(.*,)?(Print|Meta\+Shift\+R)(,|$)' /usr/share/applications/org.kde.spectacle.desktop; then
  echo "Spectacle still claims Print or Meta+Shift+R"; exit 1
fi

echo "$(/usr/bin/spark-snip --version) installed."
