"""A fake ratbagd for the tests: the same objects and property names the real daemon has (read
from a Logitech G502 HERO with `busctl introspect`), kept in a dict. It answers the three calls
RatbagBackend makes on a bus (get_all, set, call) and writes every change down in `writes`, so
a test can tell what was sent and when. Nothing here touches a real mouse."""

import copy

from sparkcontroller.mouse import (I_DEVICE, I_MANAGER, I_PROFILE, I_RESOLUTION, MANAGER_PATH,
                                   MouseError, NO_DAEMON)

DPI = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900,
       950, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300,
       2400, 2500, 2600, 2800, 3000, 3200, 3400, 3600, 3800, 4000, 4200, 4400, 4600, 4800,
       5000, 5500, 6000, 6500, 7000, 8000, 12000, 16000, 25500]
RATES = [125, 250, 500, 1000]

# (value, disabled) per slot, which slot is active and default, and which profile is active
G502 = {
    "profiles": [
        {"active": False, "rate": 1000, "slots": [(1200, 0), (2400, 0), (3200, 0), (6400, 0),
                                                  (100, 1)], "active_slot": 1, "default": 1},
        {"active": False, "rate": 1000, "slots": [(400, 0), (800, 0), (1600, 0), (2400, 0),
                                                  (100, 1)], "active_slot": 2, "default": 2},
        {"active": True, "rate": 500, "slots": [(2400, 0), (100, 1), (100, 1), (100, 1),
                                                (100, 1)], "active_slot": 0, "default": 0},
    ],
}
# The bug of 2026-11-24: the mouse sits on a disabled 100 DPI slot.
STUCK_LOW = {
    "profiles": [
        {"active": True, "rate": 1000, "slots": [(1200, 0), (2400, 0), (3200, 0), (6400, 0),
                                                 (100, 1)], "active_slot": 4, "default": 1},
        {"active": False, "rate": 1000, "slots": [(800, 0), (1600, 0), (100, 1), (100, 1),
                                                  (100, 1)], "active_slot": 0, "default": 0},
    ],
}


class FakeRatbag:
    def __init__(self, layout=None, name="Logitech G502 HERO Gaming Mouse", devices=1,
                 refuse_commit=None, down=False, forget_commit=False):
        """refuse_commit: None, or a MouseError kind ('busy', ...) the Commit raises.
        down: the daemon isn't there. forget_commit: Commit answers 0 but the mouse keeps
        its old settings (a write that didn't stick)."""
        layout = layout or G502
        self.objects, self.writes, self.commits = {}, [], 0
        self.refuse_commit, self.down, self.forget_commit = refuse_commit, down, forget_commit
        paths = []
        for d in range(devices):
            dev = f"/org/freedesktop/ratbag1/device/hidraw{d}"
            paths.append(dev)
            ppaths = []
            for pi, p in enumerate(layout["profiles"]):
                pp = f"/org/freedesktop/ratbag1/profile/hidraw{d}/p{pi}"
                ppaths.append(pp)
                rpaths = []
                for ri, (value, off) in enumerate(p["slots"]):
                    rp = f"/org/freedesktop/ratbag1/resolution/hidraw{d}/p{pi}/r{ri}"
                    rpaths.append(rp)
                    self.objects[rp] = {I_RESOLUTION: {
                        "Index": ri, "IsActive": ri == p["active_slot"],
                        "IsDefault": ri == p["default"], "IsDisabled": bool(off),
                        "Resolution": value, "Resolutions": list(DPI), "Capabilities": [2]}}
                self.objects[pp] = {I_PROFILE: {
                    "Index": pi, "Name": "", "Disabled": p.get("disabled", False),
                    "IsActive": p["active"], "ReportRate": p["rate"],
                    "ReportRates": list(RATES), "Resolutions": rpaths, "Buttons": [],
                    "Capabilities": [102]}}
            self.objects[dev] = {I_DEVICE: {"Name": name, "Model": "usb:046d:c08b:0",
                                            "Profiles": ppaths}}
        self.objects[MANAGER_PATH] = {I_MANAGER: {"APIVersion": 2, "Devices": paths}}
        self._snapshot = copy.deepcopy(self.objects)

    def _check(self):
        if self.down:
            raise MouseError(NO_DAEMON, "org.freedesktop.DBus.Error.ServiceUnknown")

    def get_all(self, path, iface):
        self._check()
        return copy.deepcopy(self.objects[path][iface])

    def set(self, path, iface, prop, sig, value):
        self._check()
        self.writes.append(("set", path, prop, value))
        self.objects[path][iface][prop] = value

    def call(self, path, iface, method):
        self._check()
        self.writes.append(("call", path, method))
        if method == "Commit":
            if self.refuse_commit:
                raise MouseError(self.refuse_commit, "refused")
            self.commits += 1
            if self.forget_commit:
                self.objects = copy.deepcopy(self._snapshot)
            else:
                self._snapshot = copy.deepcopy(self.objects)
            return 0
        parent = path.rsplit("/", 1)[0]
        siblings = [p for p in self.objects if p.rsplit("/", 1)[0] == parent
                    and iface in self.objects[p]]
        if method == "SetActive":
            for s in siblings:
                self.objects[s][iface]["IsActive"] = s == path
        elif method == "SetDefault":
            for s in siblings:
                self.objects[s][iface]["IsDefault"] = s == path
        return 0

    def state(self):
        """What the 'mouse' holds: per profile (index, active, rate, [(dpi, off, active,
        default) per slot])."""
        out = []
        for path in sorted(p for p in self.objects if "/profile/" in p):
            prof = self.objects[path][I_PROFILE]
            slots = [self.objects[r][I_RESOLUTION] for r in prof["Resolutions"]]
            out.append((prof["Index"], prof["IsActive"], prof["ReportRate"],
                        [(s["Resolution"], s["IsDisabled"], s["IsActive"], s["IsDefault"])
                         for s in slots]))
        return out
