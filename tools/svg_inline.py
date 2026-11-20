"""Inline <use href="#bot"> copies in the animated SparkOS bot for frame-by-frame rendering.

Chrome runs CSS animations inside <use> copies on their own clock, and a script can't pause or
seek them, so a frame-by-frame render would show the arm out of step with the sparks. Drawing
the robot directly (a <g> carrying the <use>'s attributes) makes every animation seekable.
The SVG looks the same; only rendering tools use this.
"""
import re


def inline_bot(svg: str) -> str:
    m = re.search(r'<g id="bot">(.*?)\n    </g>', svg, re.S)
    if not m:
        raise ValueError('no <g id="bot"> found')
    body = m.group(1)

    def repl(u):
        attrs = u.group(1).replace('href="#bot"', '').strip()
        return f'<g {attrs}>{body}</g>' if attrs else f'<g>{body}</g>'

    out, n = re.subn(r'<use ([^>]*href="#bot"[^>]*)/>', repl, svg)
    if n == 0:
        raise ValueError('no <use href="#bot"> found')
    return out
