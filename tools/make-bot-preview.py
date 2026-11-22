#!/usr/bin/env python3
"""Builds branding/preview.html: the animated SparkOS bot with the startup sound, in one
self-contained page (the SVG and the WAV are embedded), so it opens anywhere.

    python3 tools/make-bot-preview.py
"""
import base64
from pathlib import Path

root = Path(__file__).resolve().parent.parent
svg = (root / "branding/sparkos-bot-animated.svg").read_text(encoding="utf-8")
wav = base64.b64encode((root / "files/system/usr/share/sounds/sparkos/startup.wav").read_bytes()).decode()

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SparkOS bot preview</title>
<style>
  :root {{ --bg: #0a0919; --text: #f1efff; --muted: #b3b0d2; --mint: #9be8b8; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--text);
         font-family: Inter, system-ui, sans-serif; }}
  main {{ display: flex; flex-direction: column; align-items: center; gap: 20px; padding: 24px; }}
  #stage {{ width: min(420px, 90vw); aspect-ratio: 1; }}
  #stage svg {{ width: 100%; height: 100%; display: block; }}
  button {{ font: 600 15px/1 "Chakra Petch", Inter, sans-serif; letter-spacing: .04em; text-transform: uppercase;
           padding: 12px 22px; border-radius: 3px; border: 0; background: var(--mint); color: #0a0919; cursor: pointer; }}
  button:hover, button:focus-visible {{ box-shadow: 4px 0 0 #ff2e88, -4px 0 0 #22d8ff; outline: none; }}
  p {{ margin: 0; color: var(--muted); font-size: 14px; }}
</style>
</head>
<body>
<main>
  <div id="stage"></div>
  <template id="bot-svg">{svg}</template>
  <button id="play" type="button">Play with sound</button>
  <p>The sound starts 0.4 s into the animation, as it would at sign-in.</p>
</main>
<script>
  const sound = new Audio('data:audio/wav;base64,{wav}');
  const stage = document.getElementById('stage');
  const tpl = document.getElementById('bot-svg');
  const show = () => stage.replaceChildren(tpl.content.cloneNode(true));
  show();
  document.getElementById('play').addEventListener('click', () => {{
    show();   // a fresh copy restarts the animation
    sound.currentTime = 0;
    setTimeout(() => sound.play(), 400);
  }});
</script>
</body>
</html>
"""
out = root / "branding/preview.html"
out.write_text(page, encoding="utf-8", newline="\n")
print(f"wrote {out} ({len(page) / 1e6:.2f} MB)")
