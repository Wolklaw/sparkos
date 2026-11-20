"""Render the animated SparkOS bot (branding/sparkos-bot-animated.svg) to the GIF the sign-in
splash plays, frame by frame in Chrome, so Plasma's splash needs no SVG animation support.

    pip install playwright imageio-ffmpeg     (uses your installed Chrome, no browser download)
    python tools/make-splash-animation.py

Writes files/system/usr/share/plasma/look-and-feel/dev.wolklaw.sparkos.desktop/contents/splash/images/bot.gif
(560x560 on the splash background, 25 fps, plays once and holds the last frame).
Run it again whenever the animated SVG changes, and commit the GIF.
"""
import pathlib, subprocess, tempfile
import imageio_ffmpeg
from playwright.sync_api import sync_playwright
from svg_inline import inline_bot  # tools/svg_inline.py: makes the <use> copies seekable

REPO = pathlib.Path(__file__).resolve().parent.parent
SVG = REPO / "branding" / "sparkos-bot-animated.svg"
OUT = REPO / "files/system/usr/share/plasma/look-and-feel/dev.wolklaw.sparkos.desktop/contents/splash/images/bot.gif"
SIZE, FPS, LENGTH = 560, 25, 6.8
BG = "#05040f"  # the splash background

svg = inline_bot(SVG.read_text(encoding="utf-8"))
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {SIZE}px; height: {SIZE}px; background: {BG}; overflow: hidden; }}
#art svg {{ width: {SIZE}px; height: {SIZE}px; display: block; }}
</style></head><body><div id="art">{svg}</div></body></html>"""

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    page_file = tmp / "bot.html"
    page_file.write_text(html, encoding="utf-8")
    count = int(LENGTH * FPS) + 1
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(200)
        page.evaluate("document.getAnimations().forEach(a => a.pause())")
        for i in range(count):
            ms = min(i * 1000 / FPS, LENGTH * 1000 - 1)
            page.evaluate(f"document.getAnimations().forEach(a => {{ a.currentTime = {ms}; }})")
            page.screenshot(path=str(tmp / f"f{i:04d}.png"))
        browser.close()

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # One shared palette (the art has few colours), no dithering so the flat shapes stay clean,
    # and -loop -1: play once, then Qt holds the last frame.
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"),
                    "-filter_complex", "split[a][b];[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=none",
                    "-loop", "-1", str(OUT)], check=True)
print(f"{OUT.relative_to(REPO)}: {count} frames, {OUT.stat().st_size // 1024} KB")
