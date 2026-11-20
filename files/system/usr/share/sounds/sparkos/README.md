# SparkOS startup sound

`startup.wav` (about 7 seconds) is the sound of sparks: three short electric "bzzzt"s about a second apart, then a long sizzling arc that crackles away. It plays once when you sign in, while the SparkOS bot hammers its anvil (`branding/sparkos-bot-animated.svg` lands its blows on the same beats).

**It is original.** `tools/make-startup-sound.py` (variant `arc`, the default) synthesises every sample from waveforms and seeded noise. Each zap is a harsh buzz that wobbles in pitch, chopped on and off at random so it crackles, with pops of static on top. There's no recording or sample from any other work in it, and running the script again gives the identical file. It's part of SparkOS and under the same terms as this repo.

- Turn it off: `sparkos-startup-sound --off`, or untick *SparkOS startup sound* in System Settings > Autostart.
- Turn it back on: `sparkos-startup-sound --on`.
- Change it: edit a variant in `tools/make-startup-sound.py` and run it. The other variants stay for comparison: `zap` (anvil plus zaps), `cave` (anvil only, with cave echoes), and `bright`, `heavy` and `forge`.
