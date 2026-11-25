#!/usr/bin/env python3
"""Headless test of spark-compositor: virtual outputs, no GPU, no window on any screen.

  test.py /path/to/spark-compositor /path/to/outdir

Starts the compositor with three virtual outputs (2560x1440, 1080p at 1.5x, a rotated 1080p
"portrait"), connects real clients (a layer-shell client, an xdg-shell client, an XWayland
client, a lock screen, clipboard tools, a virtual keyboard), takes screenshots through
wlr-screencopy and writes them to outdir. Exits 1 on the first failed check, after
printing the compositor log.
"""
import os
import signal, re, shutil, subprocess, sys, tempfile, time

BIN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
work = tempfile.mkdtemp(prefix="spark-comp-")
rt = os.path.join(work, "run"); os.makedirs(rt, mode=0o700)
cfg = os.path.join(work, "cfg"); os.makedirs(cfg)
logf = os.path.join(OUT, "compositor.log")

with open(os.path.join(cfg, "outputs.conf"), "w") as f:
    f.write("output HEADLESS-1 mode=2560x1440@60 scale=1 pos=0,0\n"
            "output HEADLESS-2 mode=1920x1080@60 scale=1.5 pos=2560,0\n"
            "output HEADLESS-3 mode=1920x1080@60 transform=90 pos=4480,0\n")
with open(os.path.join(cfg, "compositor.conf"), "w") as f:
    f.write(f"bind Super+t exec grep SigBlk /proc/self/status > {work}/bind-ran\n"
            f"bind Super+y exec touch {work}/y-ran\n"
            "bind Super+y none\n")

env = dict(os.environ, XDG_RUNTIME_DIR=rt, SPARK_HEADLESS_OUTPUTS="3", WLR_RENDERER="pixman",
           SPARK_COMPOSITOR_CONFIG_DIR=cfg, HOME=work, WLR_LIBINPUT_NO_DEVICES="1")
for k in ("WAYLAND_DISPLAY", "DISPLAY"):
    env.pop(k, None)

procs = []
failed = []

def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        failed.append(what)

def log():
    return open(logf).read() if os.path.exists(logf) else ""

def wait_log(pat, secs=15):
    end = time.time() + secs
    while time.time() < end:
        if re.search(pat, log()):
            return True
        time.sleep(0.2)
    return False

def run(cmd, **kw):
    return subprocess.run(cmd, env=cenv, capture_output=True, text=True, timeout=30, **kw)

def start(cmd):
    p = subprocess.Popen(cmd, env=cenv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return p

comp = subprocess.Popen([BIN, "-d"], env=env, stdout=subprocess.PIPE, stderr=open(logf, "w"), text=True)
try:
    disp = comp.stdout.readline().strip()
    check(disp.startswith("WAYLAND_DISPLAY="), f"compositor started ({disp})")
    wl = disp.split("=", 1)[1]
    cenv = dict(env, WAYLAND_DISPLAY=wl)
    xd = comp.stdout.readline().strip()
    if xd.startswith("DISPLAY="):
        cenv["DISPLAY"] = xd.split("=", 1)[1]
    check(wait_log(r"output HEADLESS-3: "), "three outputs came up")

    # 1. outputs: mode, scale, transform, position as configured
    log_txt = log()
    check("HEADLESS-1: 2560x1440" in log_txt, "output 1 is 2560x1440")
    check(re.search(r"HEADLESS-2: 1920x1080.*scale 1\.50 transform 0 at 2560,0", log_txt) is not None, "output 2 is 1080p, scale 1.5, at 2560,0")
    check(re.search(r"HEADLESS-3: 1080x1920", log_txt) is not None, "output 3 is rotated to portrait 1080x1920")
    r = run(["wlr-randr"])
    check("HEADLESS-1" in r.stdout and "2560x1440" in r.stdout, "wlr-output-management lists the outputs")
    check("Transform: 90" in r.stdout, "wlr-randr sees the 90 degree transform")

    # 2. protocols the shell needs
    info = run(["wayland-info"]).stdout
    want = ["zwlr_layer_shell_v1", "xdg_wm_base", "ext_session_lock_manager_v1", "ext_foreign_toplevel_list_v1",
            "zwlr_foreign_toplevel_manager_v1", "ext_idle_notifier_v1", "xdg_activation_v1",
            "wp_fractional_scale_manager_v1", "wp_cursor_shape_manager_v1", "zwlr_output_manager_v1",
            "zwp_primary_selection_device_manager_v1", "zwlr_data_control_manager_v1", "ext_data_control_manager_v1",
            "zwlr_screencopy_manager_v1", "ext_image_copy_capture_manager_v1",
            "ext_output_image_capture_source_manager_v1", "wp_tearing_control_manager_v1",
            "wp_presentation", "zwp_pointer_constraints_v1", "zwp_relative_pointer_manager_v1",
            "zwlr_gamma_control_manager_v1", "zwp_idle_inhibit_manager_v1", "wp_viewporter",
            "zxdg_decoration_manager_v1", "zxdg_output_manager_v1"]
    open(os.path.join(OUT, "protocols.txt"), "w").write(info)
    for g in want:
        check(g in info, f"global {g}")

    # 3. layer-shell client (a background colour), then screenshots
    start(["swaybg", "-c", "#ff00ff"])
    check(wait_log(r"mapped layer surface namespace=wallpaper layer=0"), "layer-shell client mapped (swaybg)")

    # 4. xdg-shell client
    start(["foot", "--app-id=spark-test", "--title=xdg-test", "sleep", "60"])
    check(wait_log(r"mapped xdg window app_id=spark-test title=xdg-test"), "xdg-shell client mapped (foot)")

    # 5. XWayland client
    if "DISPLAY" in cenv:
        xt = start(["xterm", "-T", "x11-test", "-e", "sleep", "60"])
        check(wait_log(r"mapped x11 window app_id=XTerm", 40), "XWayland client mapped (xterm)")
        # closing an X11 window must not take the compositor down (wlroots asserts on listeners
        # left on a destroyed xwayland surface)
        xt.terminate()
        xt.wait(10)
        time.sleep(2)
        check(comp.poll() is None, "compositor survives an X11 window closing")
        # one left open: at logout the compositor stops with X11 windows still up, and their
        # surfaces go before the X11 side (it crashed in xw_dissociate on every logout)
        left = subprocess.Popen(["xterm", "-T", "x11-left", "-e", "sleep", "120"], env=cenv,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        check(wait_log(r"mapped x11 window app_id=XTerm title=x11-left", 40), "second XWayland client mapped, left open")
    else:
        check(False, "XWayland started")

    # 6a. the Spark shell's window list (spark-wl-windows, optional third argument)
    helper = sys.argv[3] if len(sys.argv) > 3 else ""
    if helper:
        try:
            r = subprocess.run([helper], input="", env=cenv, capture_output=True, text=True, timeout=10)
            out = r.stdout
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        check('"app":"spark-test"' in out,
              f"spark-wl-windows lists the open windows ({out.strip()[:120]!r})")

    # 6. clipboard and primary selection through data-control
    start(["wl-copy", "--foreground", "spark-clip"]); time.sleep(1)
    check(run(["wl-paste", "-n"]).stdout == "spark-clip", "clipboard round trip (wl-copy / wl-paste)")
    start(["wl-copy", "--foreground", "-p", "spark-primary"]); time.sleep(1)
    check(run(["wl-paste", "-p", "-n"]).stdout == "spark-primary", "primary selection round trip")

    # 7. keyboard shortcut through a virtual keyboard
    run(["wtype", "-M", "logo", "t", "-m", "logo"])
    time.sleep(1)
    check(os.path.exists(os.path.join(work, "bind-ran")), "Super+T runs its exec binding")
    run(["wtype", "-M", "logo", "y", "-m", "logo"])
    time.sleep(0.5)
    check(not os.path.exists(os.path.join(work, "y-ran")), "a later 'bind KEY none' turns a binding off")
    # programs the compositor starts must not inherit its blocked signals: a shell that ignores
    # SIGTERM outlives the logout and takes over the next session (black screens on relogin)
    blk = open(os.path.join(work, "bind-ran")).read().split()[-1] if os.path.exists(os.path.join(work, "bind-ran")) else "?"
    check(blk.strip("0") == "", f"started programs have no blocked signals (SigBlk {blk})")

    # 8. screenshots through screencopy
    time.sleep(1)
    shots = {}
    for n in ("HEADLESS-1", "HEADLESS-2", "HEADLESS-3"):
        path = os.path.join(OUT, f"{n}.png")
        r = run(["grim", "-o", n, path])
        ident = run(["identify", "-format", "%wx%h", path]).stdout if os.path.exists(path) else ""
        shots[n] = ident
        check(r.returncode == 0 and ident != "", f"screenshot of {n} through screencopy ({ident or r.stderr.strip()})")
    check(shots["HEADLESS-1"] == "2560x1440", "screenshot of output 1 is 2560x1440")
    check(shots["HEADLESS-3"] == "1080x1920", "screenshot of the rotated output is 1080x1920")
    px = run(["convert", os.path.join(OUT, "HEADLESS-2.png"), "-format", "%[hex:p{5,5}]", "info:"]).stdout
    check(px.upper().startswith("FF00FF"), f"the layer-shell background shows in the screenshot (pixel {px})")

    # 8b. an output going away and coming back: its windows move off, then return
    run(["wlr-randr", "--output", "HEADLESS-1", "--off"])
    check(wait_log(r"window app_id=spark-test moved to HEADLESS-"), "windows leave an output that is turned off")
    run(["wlr-randr", "--output", "HEADLESS-1", "--on", "--pos", "0,0"])
    check(wait_log(r"window app_id=spark-test back on HEADLESS-1"), "windows go back when the output returns")

    # 9. lock screen (ext-session-lock): lock, see it, unlock
    lock = start(["swaylock", "-c", "000000"]) if shutil.which("swaylock") else None
    if lock:
        check(wait_log(r"session locked"), "ext-session-lock: locked (swaylock)")
        time.sleep(1)
        run(["grim", "-o", "HEADLESS-1", os.path.join(OUT, "locked.png")])
        lp = run(["convert", os.path.join(OUT, "locked.png"), "-format", "%[hex:p{300,300}]", "info:"]).stdout
        check(lp.upper().startswith("000000"), f"locked screen is black (pixel {lp})")
        # a monitor reconnecting while locked: the lock client adds a surface for it, and the
        # compositor must not send "locked" a second time (wlroots aborts; it ended a session)
        run(["wlr-randr", "--output", "HEADLESS-2", "--off"])
        time.sleep(1)
        run(["wlr-randr", "--output", "HEADLESS-2", "--on", "--pos", "2560,0"])
        time.sleep(2)
        check(comp.poll() is None, "compositor survives a monitor coming back while locked")
        print(f"     swaylock status before unlock signal: {lock.poll()}")
        for _ in range(5):  # SIGUSR1 unlocks swaylock
            lock.send_signal(10)
            if wait_log(r"session unlocked", 2):
                break
        check("session unlocked" in log(), f"ext-session-lock: unlocked (swaylock exit code {lock.poll()})")

    # 10. a montage of everything, for the CI artifact
    subprocess.run(["montage"] + [os.path.join(OUT, f"{n}.png") for n in ("HEADLESS-1", "HEADLESS-2", "HEADLESS-3")]
                   + ["-tile", "3x1", "-geometry", "800x800+8+8", "-background", "#08080c", os.path.join(OUT, "montage.png")],
                   capture_output=True)

    # 11. idle: screens go off after the configured time without input, and input wakes them
    with open(os.path.join(cfg, "compositor.conf"), "a") as f:
        f.write("idle screen_off=30\n")
    comp.send_signal(signal.SIGHUP)               # reload, as Spark Settings does
    check(wait_log(r"screens off \(idle\)", 45), "idle: screens turn off after 30 s without input")
    check("Enabled: no" in run(["wlr-randr"]).stdout, "idle: outputs report off while blank")
    run(["wtype", "-k", "Escape"])
    check(wait_log(r"screens on", 10), "idle: a key press turns the screens back on")
    check("Enabled: no" not in run(["wlr-randr"]).stdout, "idle: every output is on again")
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    comp.terminate()
    try:
        code = comp.wait(10)
        # a logout ends it the same way; a crash here leaves a core dump on every logout
        check(code == 0, f"compositor exits cleanly when told to stop (exit code {code})")
    except subprocess.TimeoutExpired:
        comp.kill()
        check(False, "compositor exits when told to stop")
    shutil.rmtree(work, ignore_errors=True)

if failed:
    print("\n--- compositor log ---\n" + log()[-6000:])
    print(f"\n{len(failed)} check(s) failed")
    sys.exit(1)
print("\nall checks passed")
