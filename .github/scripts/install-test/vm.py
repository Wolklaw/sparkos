#!/usr/bin/env python3
"""Test-only VM driver for installer-install-test.yml.

  vm.py install --work W --layout L --iso ISO [--sb]
      Boots the installer ISO from a USB stick, types test-only kernel arguments at GRUB
      (a root shell on ttyS0), runs run-in-live.sh from the KSTEST disk, waits for it.
  vm.py boot --work W --layout L [--sb] [--expect-digest sha256:...]
      Boots the installed disks without the ISO, enrolls the Secure Boot key in MokManager
      the way the installer tells people to, waits for the installed system's report.

Screens are read with tesseract (GRUB, MokManager). Results go to W/results.tsv.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time

from PIL import Image, ImageOps, ImageStat

MOK_PASSWORD = "universalblue"  # the installer's own enrollment password (secureboot-enroll-key.ks)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class QMP:
    def __init__(self, path):
        for _ in range(100):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(path)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("QMP socket did not come up")
        self.f = self.s.makefile("rw")
        self.events = []
        json.loads(self.f.readline())
        self.cmd("qmp_capabilities")

    def cmd(self, execute, **args):
        msg = {"execute": execute}
        if args:
            msg["arguments"] = args
        self.f.write(json.dumps(msg) + "\n")
        self.f.flush()
        while True:
            line = self.f.readline()
            if not line:
                raise RuntimeError("QMP closed")
            r = json.loads(line)
            if "event" in r:
                self.events.append(r)
                continue
            if "error" in r:
                raise RuntimeError(f"QMP {execute}: {r['error']}")
            return r.get("return")


class Serial:
    def __init__(self, path, logpath):
        for _ in range(100):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(path)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("serial socket did not come up")
        self.buf = ""
        self.log = open(logpath, "ab")
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            try:
                data = self.s.recv(65536)
            except OSError:
                return
            if not data:
                return
            self.log.write(data)
            self.log.flush()
            with self.lock:
                self.buf += data.decode("utf-8", "replace")

    def text(self):
        with self.lock:
            return self.buf

    def send(self, s):
        self.s.sendall(s.encode())


# QEMU key names for the characters typed at GRUB and in MokManager
KEYS = {" ": ["spc"], "-": ["minus"], "_": ["shift", "minus"], "=": ["equal"], "+": ["shift", "equal"],
        ".": ["dot"], ",": ["comma"], "/": ["slash"], ":": ["shift", "semicolon"], ";": ["semicolon"],
        "'": ["apostrophe"], '"': ["shift", "apostrophe"], "(": ["shift", "9"], ")": ["shift", "0"],
        "$": ["shift", "4"], "\n": ["ret"], "|": ["shift", "backslash"], "&": ["shift", "7"], ">": ["shift", "dot"]}


class VM:
    def __init__(self, a, phase):
        self.a, self.phase, self.W = a, phase, a.work
        self.shots = os.path.join(self.W, "shots")
        os.makedirs(self.shots, exist_ok=True)
        self.n = 0
        self.t0 = time.time()

    def start(self):
        W, a = self.W, self.a
        for s in ("qmp.sock", "serial.sock"):
            try:
                os.remove(os.path.join(W, s))
            except FileNotFoundError:
                pass
        code = "/usr/share/OVMF/OVMF_CODE_4M.secboot.fd" if a.sb else "/usr/share/OVMF/OVMF_CODE_4M.fd"
        cmd = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-machine", "q35,smm=on",
               "-smp", "4", "-m", "8192",
               "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
               "-drive", f"if=pflash,format=raw,file={W}/vars.fd"]
        if a.sb:
            cmd += ["-global", "driver=cfi.pflash01,property=secure,value=on"]
        cmd += ["-device", "qemu-xhci,id=xhci"]
        disks = [("win.img", "SPARKWIN")] if a.layout == "two-disks" else []
        disks.append(("data.img", "SPARKDATA"))
        for img, serial in disks:
            cmd += ["-drive", f"file={W}/{img},format=raw,if=none,id={serial}",
                    "-device", f"nvme,serial={serial},drive={serial}"]
        if self.phase == "install":
            cmd += ["-drive", f"file={a.iso},format=raw,if=none,id=stick,readonly=on",
                    "-device", "usb-storage,bus=xhci.0,drive=stick,removable=on,bootindex=0",
                    "-drive", f"file={W}/kstest.img,format=raw,if=none,id=kst",
                    "-device", "virtio-blk-pci,drive=kst,serial=KSTEST"]
        cmd += ["-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0",
                "-vga", "virtio", "-display", "none",
                "-chardev", f"socket,id=ser0,path={W}/serial.sock,server=on,wait=off", "-serial", "chardev:ser0",
                "-qmp", f"unix:{W}/qmp.sock,server=on,wait=off"]
        log("starting: " + " ".join(cmd))
        self.p = subprocess.Popen(cmd)
        self.qmp = QMP(f"{W}/qmp.sock")
        self.ser = Serial(f"{W}/serial.sock", f"{W}/serial-{self.phase}.log")

    def alive(self):
        return self.p.poll() is None

    def shot(self, label):
        self.n += 1
        path = os.path.join(self.shots, f"{self.phase}-{self.n:03d}-{label}.png")
        try:
            self.qmp.cmd("screendump", filename=path, format="png")
        except Exception as e:  # noqa: BLE001
            log(f"screendump failed: {e}")
            return None
        return path

    def ocr(self, label="ocr", keep=False):
        path = self.shot(label)
        if not path:
            return ""
        try:
            im = Image.open(path).convert("L")
            if ImageStat.Stat(im).mean[0] < 110:
                im = ImageOps.invert(im)
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
            tmp = path + ".ocr.png"
            im.save(tmp)
            out = subprocess.run(["tesseract", tmp, "-", "--psm", "11"], capture_output=True,
                                 text=True, timeout=90).stdout
            os.remove(tmp)
        except Exception as e:  # noqa: BLE001
            log(f"ocr failed: {e}")
            out = ""
        if not keep:
            os.remove(path)
            self.n -= 1
        else:
            with open(path + ".txt", "w") as f:
                f.write(out)
        return out

    @staticmethod
    def norm(t):
        return re.sub(r"[^a-z0-9>]", "", t.lower())

    def keys(self, *combos, delay=0.25):
        for c in combos:
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in c.split("-")], **{"hold-time": 60})
            time.sleep(delay)

    def type(self, text, delay=0.04):
        for ch in text:
            if ch.isalpha() and ch.isupper():
                k = ["shift", ch.lower()]
            elif ch.isalnum():
                k = [ch]
            else:
                k = KEYS[ch]
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": x} for x in k], **{"hold-time": 40})
            time.sleep(delay)

    def stop(self, timeout=180):
        if self.alive():
            try:
                self.qmp.cmd("system_powerdown")
            except Exception:  # noqa: BLE001
                pass
            try:
                self.p.wait(timeout)
            except subprocess.TimeoutExpired:
                log("no clean power off; quitting QEMU")
                try:
                    self.qmp.cmd("quit")
                except Exception:  # noqa: BLE001
                    self.p.kill()
                self.p.wait(30)

    def minutes(self):
        return f"{(time.time() - self.t0) / 60:.0f} min"


def result(W, status, what, detail=""):
    line = f"{status}\t{what}\t{detail}"
    print(line, flush=True)
    with open(os.path.join(W, "results.tsv"), "a") as f:
        f.write(line + "\n")


def install(a):
    vm = VM(a, "install")
    fw = "UEFI with Secure Boot on" if a.sb else "UEFI (Secure Boot off)"
    vm.start()
    # Stop GRUB's 5 s countdown: tap Up until its menu is on screen
    seen = False
    deadline = time.time() + 180
    i = 0
    while time.time() < deadline and vm.alive():
        vm.keys("up", delay=0.3)
        i += 1
        if i % 6 == 0:
            t = vm.norm(vm.ocr())
            if "installsparkos" in t:
                seen = True
                break
    vm.ocr("grub-menu", keep=True)
    if not seen:
        result(a.work, "FAIL", f"ISO boots from a USB stick ({fw})", "GRUB menu not seen in 3 min")
        vm.stop(10)
        return 1
    result(a.work, "PASS", f"ISO boots from a USB stick ({fw})", "SparkOS GRUB menu on screen")
    # GRUB command line: the menu entry's own kernel and arguments, plus a root shell on
    # ttyS0 for the test (systemd.debug_shell). Nothing on the ISO is changed.
    vm.keys("c", delay=1.5)
    lines = [
        "search --no-floppy --set=root --file /images/pxeboot/vmlinuz",
        "linux /images/pxeboot/vmlinuz quiet rhgb root=live:CDLABEL=SparkOS-Live enforcing=0 rd.live.image systemd.debug_shell=ttyS0",
        "initrd /images/pxeboot/initrd.img",
    ]
    for ln in lines:
        vm.type(ln + "\n")
        time.sleep(1.5 if ln.startswith("search") else 0.5)
    time.sleep(8)  # initrd load from USB
    vm.ocr("grub-commands", keep=True)
    vm.type("boot\n")
    # Wait for the root shell, then start the install from the KSTEST disk
    start_cmd = "mkdir -p /run/kst; until mount -L KSTEST /run/kst; do sleep 2; done; cp /run/kst/run-in-live.sh /tmp/; bash /tmp/run-in-live.sh\n"
    deadline = time.time() + 420
    shell = False
    while time.time() < deadline and vm.alive():
        if re.search(r"sh-\d[\d.]*#", vm.ser.text()):
            shell = True
            break
        time.sleep(3)
    if not shell:
        log("no debug shell on ttyS0; trying the one on tty9")
        vm.ocr("no-serial-shell", keep=True)
        vm.keys("ctrl-alt-f9", delay=3)
        vm.ocr("tty9", keep=True)
        vm.type(start_cmd)
    else:
        # What a person sees on the live system: the desktop with the installer prompt, or a
        # sign-in screen (livesys sets up autologin for SDDM; SparkOS uses Plasma Login)
        def wait_prompt(secs):
            t, end = "", time.time() + secs
            while time.time() < end:
                t = vm.norm(vm.ocr())
                if "sparkosinstaller" in t or "installsparkos" in t:
                    return True, t
                time.sleep(4)
            return False, t

        prompt, t = wait_prompt(150)
        vm.ocr("live-session", keep=True)
        if prompt:
            result(a.work, "PASS", "Live session opens the desktop by itself", "no sign-in screen")
        else:
            # Plasma Login's idle screen shows only a clock: a key shows the password box
            result(a.work, "FAIL", "Live session opens the desktop by itself",
                   "stops at the sign-in screen (Live System User)")
            vm.keys("ret", delay=4)
            vm.ocr("live-sign-in", keep=True)
            vm.keys("ret", delay=2)
            prompt, t = wait_prompt(120)
            vm.ocr("live-after-enter", keep=True)
            result(a.work, "PASS" if "password" not in t else "FAIL",
                   "Pressing Enter (empty password) signs in to the live desktop",
                   "desktop after Enter" if "password" not in t else "still at the sign-in screen")
        result(a.work, "PASS" if prompt else "FAIL", "The SparkOS installer prompt appears on the live desktop",
               "Install SparkOS / Edit partitions / Close" if prompt else "not seen")
        vm.ser.send(start_cmd)
    last = time.time()
    deadline = time.time() + a.timeout * 60
    m = None
    while time.time() < deadline and vm.alive():
        m = re.search(r"KSTEST-RESULT rc=(\d+)", vm.ser.text())
        if m:
            break
        if time.time() - last > 150:
            vm.shot(f"install-{vm.minutes().replace(' ', '')}")
            last = time.time()
        time.sleep(5)
    vm.shot("install-end")
    stages = re.findall(r"KSTEST-STAGE [^\r\n]*", vm.ser.text())
    log("stages: " + " | ".join(stages))
    if not m:
        why = "VM stopped" if not vm.alive() else f"no result after {a.timeout} min"
        result(a.work, "FAIL", "Installer ran to the end", f"{why}; last stage: {stages[-1] if stages else 'none'}")
        vm.stop(60)
        return 1
    rc = int(m.group(1))
    vm.stop(240)
    if rc == 0:
        result(a.work, "PASS", "Installer ran to the end", f"Anaconda exit code 0, {vm.minutes()} from power on")
        return 0
    result(a.work, "FAIL", "Installer ran to the end", f"exit code {rc} (98: failure in anaconda.log)")
    return 1


def boot(a):
    vm = VM(a, "boot")
    vm.start()
    state = "wait"
    steps = {  # state: (text that shows it, keys, next state)
        "wait": ("pressanykeytoperformmok", ["ret"], "menu"),
        "menu": ("enrollmok", ["down", "ret"], "enroll"),
        "enroll": ("viewkey", ["down", "ret"], "confirm"),
        "confirm": ("enrollthekey", ["down", "ret"], "password"),
        "password": ("password", None, "reboot"),
        "reboot": ("reboot", ["ret"], "done"),
    }
    mok_seen = False
    since = time.time()
    deadline = time.time() + 25 * 60
    last_shot = 0
    while time.time() < deadline and vm.alive():
        if "=== SPARKOS-CHECK-END" in vm.ser.text():
            break
        if state != "done":
            t = vm.norm(vm.ocr())
            # On the first start MokManager opens straight on its menu (no "press any key")
            if state == "wait" and "enrollmok" in t and "continueboot" in t:
                log("MokManager: opened on its menu")
                mok_seen, state, since = True, "menu", time.time()
            want, keys, nxt = steps[state]
            hit = ("anykey" in t and "mok" in t) if state == "wait" else want in t
            # MokManager waits forever (mokutil --timeout -1); later screens get a blind try
            # after 40 s so a misread doesn't stall the test (the result is checked anyway)
            if hit or (state != "wait" and time.time() - since > 40):
                if state == "wait":
                    mok_seen = True
                log(f"MokManager: {state} ({'seen' if hit else 'not read, trying anyway'})")
                vm.ocr(f"mok-{state}", keep=True)
                if keys:
                    vm.keys(*keys, delay=0.8)
                else:
                    vm.type(MOK_PASSWORD + "\n", delay=0.15)
                state, since = nxt, time.time()
                time.sleep(2)
                continue
            if state == "wait" and time.time() - since > 300:
                log("no MokManager screen in 5 min; going on without it")
                state = "done"
        if time.time() - last_shot > 45:
            vm.shot("booting")
            last_shot = time.time()
        time.sleep(1.5)
    text = vm.ser.text()
    done = "=== SPARKOS-CHECK-END" in text
    signin = vm.ocr("sign-in-screen", keep=True)
    vm.stop(240)
    W = a.work
    if a.sb or mok_seen:
        result(W, "PASS" if mok_seen and state == "done" else ("FAIL" if a.sb else "WARN"),
               "MokManager: Secure Boot key enrolled with the installer's password",
               "Enroll MOK > Continue > Yes > password > Reboot" if mok_seen else "MokManager screen not seen")
    if not done:
        result(W, "FAIL", "Installed SparkOS boots without the ISO", "no report from the installed system in 25 min")
        return 1
    block = text[text.rfind("=== SPARKOS-CHECK-BEGIN"):text.rfind("=== SPARKOS-CHECK-END")]
    with open(os.path.join(W, "installed-check.txt"), "w") as f:
        f.write(block.replace("\r", ""))
    c = dict(re.findall(r"^CHECK (\w+)=([^\r\n]*)", block, re.M))
    result(W, "PASS", "Installed SparkOS boots without the ISO", f"{c.get('pretty', '?')}, kernel {c.get('kernel', '?')}")
    result(W, "PASS" if c.get("name", "").startswith("SparkOS") else "FAIL", "os-release says SparkOS",
           f"NAME={c.get('name')} ID={c.get('id')} VERSION_ID={c.get('version')}")
    img, dig = c.get("booted_image", ""), c.get("booted_digest", "")
    result(W, "PASS" if img.startswith("ghcr.io/wolklaw/sparkos") else "FAIL",
           "bootc follows the signed SparkOS image", f"{c.get('booted_transport')}:{img}")
    if a.expect_digest:
        result(W, "PASS" if dig == a.expect_digest else "FAIL", "Booted image is the one the ISO was built from",
               f"{dig[:19]}... (release notes: {a.expect_digest[:19]}...)")
    else:
        result(W, "INFO", "Booted image digest", dig)
    dm = c.get("dm", "")
    words = [w for w in ("sparktest", "spark test", "password", "log in", "login") if w in signin.lower()]
    result(W, "PASS" if dm.startswith("active") else "FAIL", "Sign-in screen is up",
           f"display-manager {dm}; on screen: {', '.join(words) or 'see screenshot'}")
    tgt = c.get("default_target", "")
    result(W, "PASS" if tgt == "graphical.target" else "FAIL", "Installed system starts to the graphical sign-in", tgt)
    al = c.get("autologin", "").strip()
    result(W, "PASS" if not al else "FAIL", "Installed system asks for a password (no autologin)",
           "no autologin user set" if not al else f"autologin: {al}")
    be = c.get("boot_entry", "").strip()
    result(W, "PASS" if be.startswith("SparkOS") else "FAIL", "Firmware boot entry is named SparkOS",
           be or "BootCurrent not found")
    sb = c.get("sb", "")
    if a.sb:
        result(W, "PASS" if "enabled" in sb.lower() else "FAIL", "Booted with Secure Boot on", sb)
    else:
        result(W, "INFO", "Secure Boot state", sb)
    result(W, "PASS" if "btrfs" in c.get("root_fs", "") else "WARN", "Root file system is btrfs", c.get("root_fs", ""))
    failed = c.get("failed_units", "").strip()
    result(W, "INFO" if not failed else "WARN", "Failed units on the installed system", failed or "none")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["install", "boot"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--iso")
    ap.add_argument("--sb", action="store_true")
    ap.add_argument("--expect-digest", default="")
    ap.add_argument("--timeout", type=int, default=120, help="install minutes")
    a = ap.parse_args()
    sys.exit(install(a) if a.phase == "install" else boot(a))


if __name__ == "__main__":
    main()
