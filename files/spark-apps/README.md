# Spark Apps (live app updates)

The part of SparkOS that installs signed Spark app updates without a reboot. The full
write-up (trust chain, rollback, failure modes) is [docs/app-updates.md](../../docs/app-updates.md).

| Path | What it is |
|---|---|
| `sparkapps/` | the library: `index` (signed index checks), `archive` (safe extraction), `fetch` (HTTPS download), `choose` (live or built-in), `store` (state and the update run), `selftest` |
| `launch.py` | what `/usr/bin/spark-<app>` runs: picks the live copy if it passes every check, else the built-in one |
| `spark-apps-update` | the root service, installed as `/usr/libexec/spark-apps-update` |
| `systemd/`, `polkit/` | the hourly timer, the service, the `spark-apps-now@` units and the polkit rule that lets the owner start only those |
| `ci/appindex.py` | release side: which apps changed, bundle build, index payload, envelope, verify |
| `install.sh` | image build step (`--deps`, `--key`) and `--uninstall` |
| `tests/` | unit tests and a local end-to-end run (`python3 -m unittest discover -s tests`) |

Root code never comes from the live area. The live area holds only the apps' own user-space code.
