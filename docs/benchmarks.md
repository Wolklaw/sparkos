# SparkOS vs Windows 11: game benchmarks

Same PC, same game, same in-game settings, booted into one system and then the other. These are one person's runs on one PC, not a lab test.

## The PC

- Ryzen 7 7800X3D, Radeon RX 6800 XT, 2560x1440 monitor at 180 Hz
- Windows 11 and SparkOS on the same machine (dual boot)
- SparkOS: image 45.20261117.1, kernel 7.3.4, Mesa 26.2.7, Steam (Flatpak) with Proton Experimental 11.0 (12 Nov 2026)

## Results

### Marvel's Spider-Man 2

The same 90-second run in the game, HDR on in the game on both systems.

| | Windows 11 | SparkOS | Difference |
|---|---|---|---|
| Average FPS | 78.6 | **92.4** | **+18%** |
| 1% lows | 48.4 | **62.6** | **+29%** |
| Runs | 3 (21 Nov 2026) | 2 (22 Nov 2026) | |

Per run, average FPS (1% low):

- Windows 11: 79.3 (46.0), 78.1 (50.3), 78.5 (48.8)
- SparkOS, HDR on: 93.0 (63.1), 91.7 (62.0)

Extra SparkOS runs on the same evening, to see what HDR costs:

- HDR off on the desktop and in the game: 92.6 (63.0), 93.3 (63.7), 92.4 (61.4), so 92.8 on average. HDR on or off makes no measurable difference.
- Four earlier runs (desktop HDR on, game HDR off) averaged 91.6. Their lows aren't counted: the game was alt-tabbed during those runs.

### Clair Obscur: Expedition 33

Not compared yet. Windows 11 did 79.0 FPS on average over 4 runs (1% lows about 24); the SparkOS runs are still to do.

## How it was measured

- **Recording:** PresentMon on Windows, MangoHud on SparkOS (set up and started with Spark Bench). Both log the time of every frame.
- **Same math for both:** each run is cut to the stretch from 5 to 80 seconds, so loading and the menu at the end don't count. Average FPS is frames divided by time. The 1% low is the average of the slowest 1% of frames, as frame rate.
- **HDR on SparkOS:** Proton Experimental 11 has no Wayland driver, so the game can't turn on HDR by itself. The HDR runs went through gamescope (`gamescope -W 2560 -H 1440 -r 180 -f --hdr-enabled -- env ENABLE_GAMESCOPE_WSI=1 DXVK_HDR=1 %command%`). The game rendered in HDR, but the picture looked gray on the desktop: the hand-off from gamescope to KDE isn't right yet. That doesn't change the frame rate.

## Limits

- One PC, an all-AMD one. Results on NVIDIA or Intel graphics, or other games, may differ.
- Two or three runs per setup. Run-to-run spread was about 2 FPS on SparkOS.
- The Windows GPU driver version wasn't noted.
