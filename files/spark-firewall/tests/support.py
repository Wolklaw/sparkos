"""Shared by the tests: firewalld output as the owner's PC printed it (read only, 2026-11-23), and
a fake runner that answers from it. Nothing here touches the real firewall."""

import os
import sys
import tempfile
from typing import Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for _var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(_var, tempfile.mkdtemp(prefix=f'spark-firewall-{_var.lower()}-'))

WORKSTATION = """FedoraWorkstation (default, active)
  target: default
  ingress-priority: 0
  egress-priority: 0
  icmp-block-inversion: no
  interfaces: eno1
  sources:
  services: dhcpv6-client samba-client ssh
  ports: 1025-65535/udp 1025-65535/tcp
  protocols:
  forward: yes
  masquerade: no
  forward-ports:
  source-ports:
  icmp-blocks:
  rich rules:
"""

PUBLIC = """public
  target: default
  ingress-priority: 0
  egress-priority: 0
  icmp-block-inversion: no
  interfaces:
  sources:
  services: dhcpv6-client mdns ssh
  ports:
  protocols:
  forward: yes
  masquerade: no
  forward-ports:
  source-ports:
  icmp-blocks:
  rich rules:
"""

SERVICES = ("dhcpv6-client http https kdeconnect mdns nova samba samba-client spark-link ssh "
            "steam-lan-transfer steam-streaming syncthing warpinator")
SERVICE_INFO = {
    "steam-streaming": "steam-streaming\n  ports: 27036/tcp 27037/tcp 27031-27036/udp 10400/udp "
                       "10401/udp\n  protocols: \n",
    "spark-link": "spark-link\n  ports: 47100/tcp\n  protocols: \n",
    "nova": "nova\n  ports: 8765/tcp 8766/udp 8780/tcp\n  protocols: \n",
    "ssh": "ssh\n  ports: 22/tcp\n  protocols: \n",
    "http": "http\n  ports: 80/tcp\n  protocols: \n",
}
NMCLI = ("Wired connection 1:5b9c2d4e-1f2a-4c3b-8d9e-0a1b2c3d4e5f:802-3-ethernet:eno1\n"
         "tailscale0:7c1d2e3f-aaaa-bbbb-cccc-0123456789ab:tun:tailscale0\n"
         "lo:00000000-0000-0000-0000-000000000000:loopback:lo\n")


class FakeRun:
    """A runner that answers like the PC did and records every command line it was given."""

    def __init__(self, running: bool = True, workstation: bool = True):
        self.running = running
        self.calls: List[List[str]] = []
        self.zones: Dict[str, str] = {"FedoraWorkstation" if workstation else "public":
                                      WORKSTATION if workstation else PUBLIC}
        self.zones.setdefault("public", PUBLIC)
        self.default = "FedoraWorkstation" if workstation else "public"
        self.fail_on: str = ""

    def __call__(self, argv: List[str]) -> Tuple[int, str, str]:
        self.calls.append(list(argv))
        if self.fail_on and self.fail_on in " ".join(argv):
            return 1, "", "Error: INVALID_SERVICE: nope"
        cmd = argv[0]
        if cmd == "systemctl":
            return (0, "enabled\n", "") if argv[1] == "is-enabled" else (0, "", "")
        if cmd == "nmcli":
            return 0, NMCLI, ""
        if cmd != "firewall-cmd":
            return 127, "", "not found"
        arg = argv[1]
        if arg == "--state":
            return (0, "running\n", "") if self.running else (252, "not running\n", "")
        if not self.running:
            return 252, "", "FirewallD is not running"
        if arg == "--get-default-zone":
            return 0, self.default + "\n", ""
        if arg == "--get-zones":
            return 0, "FedoraServer FedoraWorkstation block dmz drop external home internal " \
                      "nm-shared public trusted work\n", ""
        if arg == "--get-services":
            return 0, SERVICES + "\n", ""
        if arg == "--get-active-zones":
            return 0, f"{self.default}\n  interfaces: eno1\n", ""
        if arg.startswith("--zone=") and argv[2] == "--list-all":
            name = arg.split("=", 1)[1]
            return (0, self.zones[name], "") if name in self.zones else (1, "", "INVALID_ZONE")
        if arg.startswith("--get-zone-of-interface="):
            return (0, self.default + "\n", "") if arg.endswith("eno1") else (1, "no zone\n", "")
        if arg.startswith("--info-service="):
            name = arg.split("=", 1)[1]
            return 0, SERVICE_INFO.get(name, f"{name}\n  ports: \n"), ""
        return 0, "success\n", ""
