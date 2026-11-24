"""The rules people actually want, in plain words. Each one is a firewalld service that ships with
Fedora (or with SparkOS, for Spark Link and Nova), so turning it on adds that service to the zone and
nothing else. A rule whose service this PC's firewalld doesn't define is not shown. The words are
in text.py under rule.<id>.title and rule.<id>.detail."""

from typing import List, NamedTuple


class Rule(NamedTuple):
    id: str
    service: str


RULES: List[Rule] = [
    Rule("steam_remote_play", "steam-streaming"),
    Rule("steam_transfer", "steam-lan-transfer"),
    Rule("spark_link", "spark-link"),
    Rule("nova", "nova"),
    Rule("kde_connect", "kdeconnect"),
    Rule("find_devices", "mdns"),
    Rule("file_sharing", "samba"),
    Rule("remote_login", "ssh"),
    Rule("syncthing", "syncthing"),
    Rule("warpinator", "warpinator"),
    Rule("web_http", "http"),
    Rule("web_https", "https"),
]

KNOWN_SERVICES = {rule.service: rule for rule in RULES}


def available(services: List[str]) -> List[Rule]:
    return [rule for rule in RULES if rule.service in services]


# Zones in everyday words. A zone not listed here is shown by its own name.
ZONE_WORDS = {
    "sparkos": "zone.sparkos",
    "public": "zone.public",
    "home": "zone.home",
    "work": "zone.work",
    "internal": "zone.internal",
    "trusted": "zone.trusted",
    "block": "zone.block",
    "drop": "zone.drop",
    "dmz": "zone.dmz",
    "external": "zone.external",
    "FedoraWorkstation": "zone.fedoraworkstation",
    "FedoraServer": "zone.fedoraserver",
    "nm-shared": "zone.nm_shared",
}
# What a person should be offered for a network: not the server, router or sharing zones
CHOOSABLE = ("sparkos", "public", "home", "work", "trusted", "block", "FedoraWorkstation")
