# SparkOS startup sound

`startup.wav` (about 6 seconds) is a hammer ringing on an anvil in a cave. There are three slow blows, each a bright "ting" followed by the lighter "tink" of the hammer bouncing back, about a second apart. Then a heavier final blow rings out. Each blow echoes back off the walls. It plays once when you sign in.

**It is original.** `tools/make-startup-sound.py` (variant `cave`, the default) synthesises every sample from sine waves and seeded noise. The ring comes from the partials of a steel anvil, which aren't in a musical ratio. There's no recording or sample from any other work in it, and running the script again gives the identical file. It's part of SparkOS and under the same terms as this repo.

- Turn it off: `sparkos-startup-sound --off`, or untick *SparkOS startup sound* in System Settings > Autostart.
- Turn it back on: `sparkos-startup-sound --on`.
- Change it: edit the rhythm, pitch or echo of a variant in `tools/make-startup-sound.py` and run it. The other variants (`bright`, `heavy`, `forge`) are kept for comparison.
