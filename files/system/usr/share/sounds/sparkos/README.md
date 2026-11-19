# SparkOS startup sound

`startup.wav` is a hammer striking steel in a cave: three working blows, then a heavier final one, with the echo of a rocky room. It plays once when you sign in.

**It is original.** `tools/make-startup-sound.py` synthesises every sample from sine waves and seeded noise. There's no recording or sample from any other work in it, and running the script again gives the identical file. It's part of SparkOS and under the same terms as this repo.

- Turn it off: `sparkos-startup-sound --off`, or untick *SparkOS startup sound* in System Settings > Autostart.
- Turn it back on: `sparkos-startup-sound --on`.
- Change it: edit the rhythm, pitch or echo in `tools/make-startup-sound.py` and run it.
