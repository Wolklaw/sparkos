# Spark Calc

The SparkOS calculator: standard, scientific and programmer modes. Sums are exact: 0.1 + 0.2 is 0.3, and 1 ÷ 3 × 3 is 1.

It follows the PC's language: French when the system language is French (`LANG=fr_CA.UTF-8`, for example), English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run. In French it writes and reads a decimal comma (`1,5 + 2` is 3,5), the keypad's decimal key types it, and a function's numbers are separated with `;` (`round(2,5; 1)`). `spark-calc --eval` keeps the point, for scripts.

SparkOS has had no calculator since KCalc went. Spark Calc is an optional Spark app: it installs for one user without root (`install.sh --user`), the way optional apps will through the future Spark Portal. It also has an image build step ([files/scripts/spark-calc.sh](../scripts/spark-calc.sh)) in case the owner decides to ship it in the image; the recipe doesn't use it yet.

- **Standard:** the layout people know from Windows: %, CE, C, backspace, 1/x, x², √x, the four operations, ± and =.
- **Scientific:** sin, cos, tan and their inverses in degrees or radians, sinh, cosh, tanh, ln, log, eˣ, powers, roots (√x and ʸ√x), n!, mod, π, e, brackets.
- **Programmer:** HEX, DEC, OCT and BIN side by side (click one to type in that base), 8, 16, 32 or 64-bit, AND, OR, XOR, NOT, NAND, NOR, shifts and rotations. Numbers are two's complement, like the processor holds them; a result that doesn't fit wraps around and the display says so.
- **Typing:** type whole sums as well as clicking. The answer shows as you type (`= 5`); Enter or = works it out. Keys such as √x, x², 1/x, sin and ± act on the number just before the cursor (type 9, press √x: `√9`), or on the answer after =. A digit after = starts a new sum; an operator carries on from the answer.
- **History** of the last 100 sums, newest first: click a sum to edit it again, or its answer to use it. Up and Down bring earlier sums back into the entry. Kept in `~/.local/state/spark-calc/history.json`; Clear empties it.
- **Memory:** MC, MR, M+, M−, MS.

| Keys | |
|---|---|
| Enter, = | Work it out |
| Esc | Clear |
| Backspace, Delete, arrows, Home, End | Edit the sum |
| Up / Down | Earlier sums from the history |
| Ctrl+C | Copy the answer (or the selected text) |
| Ctrl+A | Select the whole sum |
| Ctrl+V | Paste a sum or a number (1,234.5 loses its thousands separators) |
| F9 | Change the sign of the last number |
| Ctrl+1 / 2 / 3 | Standard / Scientific / Programmer |
| Ctrl+H | Show or hide the history |
| Ctrl+M, Ctrl+P, Ctrl+Q, Ctrl+R, Ctrl+L | MS, M+, M−, MR, MC |
| Ctrl+W | Close |

The Spark compositor binds the keyboard's Calculator key (`XF86Calculator`) to Spark Calc; change it in Spark Settings > Shortcuts.

## How it counts

Spark Calc reads sums with its own tokenizer and recursive-descent parser ([sparkcalc/engine.py](sparkcalc/engine.py), [sparkcalc/programmer.py](sparkcalc/programmer.py)). Python's `eval` is never used.

- **Exact while it can be.** Numbers are fractions (Python's `fractions`), so decimals typed in are kept exactly: 0.1 is 1/10, not the nearest binary fraction. 2^200 keeps all its digits.
- **60 digits when it can't.** Results that are irrational (√2, π, sin 45°, ln 2) are worked out with Python's `decimal` to 60 significant digits; Spark Calc computes π, the trigonometric and hyperbolic functions itself from series. If a result comes out within rounding error of a short number, it becomes exact again: asin(0.5) in degrees is 30, √2² is 2, and √2² − 2 is 0 (not 1e-59).
- **Shown to 20 digits.** Answers are rounded to 20 significant digits for display, and in scientific notation past 10²⁰ or below 10⁻⁹ (`1.5e+25`). When an answer is rounded, the display says so and the line above shows ≈ instead of =. The exact value is kept while Spark Calc is open: 1 ÷ 3 =, then × 3 = gives 1, not 0.99999999999999999999 (the history file stores answers as shown).
- **Degrees are exact too.** sin 30°, cos 60°, tan 45° and the other multiples of 30° and 45° that have rational values come out exact; tan 90° says it has no value.
- **Limits.** Numbers must stay below 10¹⁰⁰⁰⁰; below 10⁻¹⁰⁰⁰⁰ they become 0. Factorials go up to 3248!. Trigonometry takes angles below 10¹⁰⁰. A sum can be 10,000 characters and nest 64 levels deep. Anything bigger stops with a sentence saying why instead of hanging.

### What it reads

| | |
|---|---|
| Operators | `+ − × ÷` (or `- * /`), `^` or `**` for powers, `mod`, postfix `!`, `%`, `²`, `³` |
| Order | brackets, then `! % ² ³`, then `^` (right to left: 2^3^2 is 512), then a leading minus (−2^2 is −4), then `× ÷ mod`, then `+ −` |
| Percent | `200 + 10%` is 220, `200 − 10%` is 180 (a percent of the left side); `200 × 10%` is 20; `50%` alone is 0.5 |
| Implicit × | `2π`, `2(3+4)`, `(1+2)(3+4)`, `3 sin 30`; two plain numbers side by side (`5 3`) are an error |
| Functions | `sin cos tan sec csc cot asin acos atan sinh cosh tanh asinh acosh atanh sqrt √ cbrt root(x, n) exp ln log log(x, base) log2 log10 abs floor ceil round round(x, places)` |
| Without brackets | `√9`, `sin 30`, `ln 2` take the next number (like a minus sign: `√2^2` is √4) |
| Constants | `π` or `pi`, `e`, `ans` (the last answer) |
| Numbers | `12`, `.5`, `1.5e+25`, `2e3`; `2e` is 2 × e |
| Brackets | a missing `)` at the end is added, like most calculators |
| `mod` | the remainder takes the sign of the left side (−7 mod 3 is −1), like the Windows calculator |

Programmer mode reads numbers in the chosen base (`0x`, `0o` and `0b` prefixes work too; `0b` not in HEX, where `0b1` is the hex number B1; `_` groups digits). Operators, loosest first, as in C: `|` `or` `nor`; `^` `xor` (`^` is XOR here, not a power); `&` `and` `nand`; `<<` `>>` `>>>` `rol` `ror` (`>>` keeps the sign, `>>>` fills with zeros); `+ −`; `× ÷ % mod` (division rounds toward zero); then `−` `~` `not` in front of a number. Each step wraps to the word size: 127 + 1 in 8 bits is −128, and the display says it wrapped. Switching word size wraps the current value; switching between Standard and Programmer carries the value across (decimals are dropped).

Errors say what is wrong and put the cursor where it is: "Can't divide by zero.", "The sum isn't finished.", "There's a ")" without a "(".", "“2” isn't a BIN digit.", "A negative number has no real square root.", "Too big: Spark Calc works below 10^10000." Every sentence is in [sparkcalc/text.py](sparkcalc/text.py), ready for a French table.

## Speed

Target from the brief: open in under 0.3 s.

Measured by CI on 2026-11-20 (GitHub runner: 4 vCPUs of an AMD EPYC 9V74, Fedora, Python 3.15, Tk 9.0, Xvfb), second launch of each mode:

| Mode | First paint, from process start | Per sum (keys to answer on screen, history saved) |
|---|---|---|
| Standard | 0.12 s | 4.5 ms average, 23 ms slowest |
| Scientific | 0.12 s | 3.2 ms average, 6.5 ms slowest |
| Programmer | 0.12 s | 5.0 ms average, 9.9 ms slowest |

The target is met on Linux. On the owner's Windows PC (Python 3.13, Tk 8.6) the same takes 0.28 to 0.32 s from the app's code being loaded, mostly Tk starting up, which is slower on Windows. It hasn't been measured on a SparkOS desktop yet; `spark-calc --bench --mode standard` does it on any PC.

Nothing runs while it waits: no timers except the house glitch every 7 to 12 seconds, which stops when the desktop asks for no animation.

## Install, run, test

```
bash install.sh --user                    # just you, into ~/.local; no root
bash install.sh --user --uninstall        # removes exactly what --user installed
sudo bash install.sh --deps               # system-wide, with Fedora packages (the image build step)
spark-calc                                # or the Calculator key
spark-calc --mode programmer              # open in a mode
spark-calc --eval '0.1+0.2'               # print an answer, no window
spark-calc --eval 'FF and 0F' --mode programmer --base hex --bits 8
spark-calc --self-test                    # checks Python, Tk and a set of sums; no display needed
spark-calc --bench --mode scientific      # time to first paint, and a few sums through the window
python3 -m unittest discover -s tests -v
python3 make_icons.py                     # redraw icons/ after changing the mark (needs Pillow)
```

`--user` needs only what the SparkOS image already has (Python 3 with tkinter). It installs to `~/.local/lib/spark-calc/`, `~/.local/bin/spark-calc`, `~/.local/share/applications/`, and `~/.local/share/icons/`, and lists every file it wrote in `~/.local/lib/spark-calc/installed-files` for `--uninstall`. Settings (`~/.config/spark-calc/`) and history (`~/.local/state/spark-calc/`) are left in place by `--uninstall`.

`spark-app.json` describes the app for the Spark Portal (ID, name, summary, version, size, what it needs, how to install it).

The tests ([tests/](tests)) cover the parser (order of operations, implicit multiplication, percent, every function, exactness, every error and where it points, division by zero, numbers near the 10¹⁰⁰⁰⁰ limit and past Python's 4,300-digit limit, nesting and length limits, and that nothing takes over a second), programmer mode (bases, word sizes, bitwise operators, shifts, rotations, overflow wrapping and when it is reported), what each key does to the text, the window under a display (keys, keyboard, memory, history, modes, settings) and the command line and `--user` install. CI ([workflow](../../.github/workflows/spark-calc.yml)) runs the build step and all tests under Xvfb in Fedora and measures the speed, and inside the published SparkOS image installs it with `--user` as a normal user, runs the self-test and the unit tests, and uninstalls it.

## Known gaps

- **Opened on a real SparkOS desktop in CI, not used by hand yet.** The boot test opens it from the app menu in the Spark session in a VM, in English and in French, waits for its window, keeps a screenshot and fails on a Python traceback. The Calculator key goes through the compositor's `XF86Calculator` bind; that hasn't been tried on hardware.
- **English and Quebec French**, picked from the PC's language (`SPARK_LANG=en|fr` overrides it). In French, numbers are typed and shown with a decimal comma (0,5) and spaces between thousands; every sentence is in `sparkcalc/text.py`.
- **No complex numbers**, so √−1 is an error. No unit conversion, graphing or date arithmetic.
- **Programmer mode** has no grid of clickable bits, and is always signed (two's complement); there is no unsigned DEC view.
- Standard mode follows the order of operations (2 + 3 × 4 is 14), because the whole sum is visible. The Windows calculator's Standard mode works left to right instead (20).
