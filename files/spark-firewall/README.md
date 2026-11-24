# Spark Firewall

The firewall in plain words: on or off, which zone each network is in, and plain-language rules such as "Allow Steam Remote Play" and "Allow Spark Link". It replaces firewall-config and works through firewalld.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Spark Firewall ships in the SparkOS image ([build step](../scripts/spark-firewall.sh)). It installs system-wide only (`sudo bash install.sh --deps`), because changing firewalld needs root. Design and the reasons for the choices: [briefs/spark-firewall.md](../../briefs/spark-firewall.md).

- **Overview:** running or stopped, on at boot, the default zone, how much is open. Turn the firewall on or off. A zone for each network.
- **Rules:** one switch per plain rule for the chosen zone. A rule says what it opens and whether the zone already covers it (Fedora's default zone opens every port from 1025 up).
- **Ports:** every service and port a zone opens, with Remove, and Add port (TCP or UDP).

Nothing changes until you press Apply, and Apply asks for your password once (polkit). Reading the firewall needs no password. Settings are in `~/.config/spark-firewall/`.

## Tests

```
cd files/spark-firewall
python3 -m unittest discover -s tests -v
SPARK_LANG=fr python3 -m unittest discover -s tests -v
```

They use a fake runner and firewalld output recorded on a real PC. Nothing changes a firewall. Window tests are skipped without a display. `spark-firewall --self-test` only reads.
