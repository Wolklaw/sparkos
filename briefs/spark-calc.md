# Spark Calc

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-calc/`, `install.sh` with `--deps` and `--user`, `spark-app.json`,
`--self-test`, tests, workflow, build step `files/scripts/spark-calc.sh`). Don't edit
`recipes/recipe.yml` or `boot-test.yml`; the main session wires it in at merge.

## Why

SparkOS has no calculator (KCalc was removed with Bazzite's first-boot apps). The owner wants
small, fast Spark tools instead of other projects' apps ([PLAN.md](../PLAN.md)).

## What it does

- **Standard** (the Windows Calculator layout people know), **Scientific** (trig in degrees or
  radians, powers, roots, logs, factorial, constants, parentheses) and **Programmer** (hex, dec,
  oct and bin side by side; bitwise operators; 8/16/32/64-bit) modes.
- Type expressions as well as click; full keyboard support (Enter, Esc, Backspace, Ctrl+C/V for
  the result or a pasted expression).
- Exact decimal arithmetic for everyday sums (`0.1 + 0.2` is `0.3`): Python's `decimal` and
  `fractions` with a small expression parser written for it, never `eval`.
- History panel (click to reuse) and memory keys.
- Opens in under 0.3 s.

## Done when

CI passes in Fedora and inside `ghcr.io/wolklaw/sparkos:latest` (switch users with `setpriv`),
the parser has thorough tests (precedence, errors, division by zero, huge numbers, programmer-mode
overflow), the build step exists, and a PR from `spark-calc` is open for the owner.
