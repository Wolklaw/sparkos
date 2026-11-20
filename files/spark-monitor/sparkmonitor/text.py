"""Every sentence the interface shows, in one place, so a French translation can be added as
a second table. t('key', name=...) fills in the blanks."""

from .desktop import languages

EN = {
    # tabs and headings
    'tab.apps': "Apps",
    'tab.performance': "Performance",
    'tab.startup': "Startup",
    'tab.details': "Details",
    'section.app': "Apps",
    'section.background': "Background",
    'section.system': "System",
    'col.name': "Name",
    'col.cpu': "CPU",
    'col.memory': "Memory",
    'col.gpu': "GPU",
    'col.disk': "Disk",
    'col.pid': "PID",
    'col.user': "User",
    'col.state': "State",
    'col.nice': "Nice",
    'col.command': "Command line",
    'col.status': "Status",
    'col.origin': "Set by",
    'col.about': "Description",

    # status line
    'status.watching': "WATCHING",
    'status.paused': "PAUSED WHILE HIDDEN",
    'status.test_data': "TEST DATA",

    # Apps tab
    'apps.summary': "{procs} processes · {apps} apps",
    'apps.end': "End task",
    'apps.system_note': "Part of the desktop or the system. Ending it can log you out or "
                        "freeze the screen, so Spark Monitor won't from here. "
                        "Details can, if you're sure.",
    'apps.self_note': "This is Spark Monitor. Close it with the window's X.",
    'apps.not_mine': "Runs as another user. Spark Monitor can only end your own apps.",

    # ending
    'end.ending': "ENDING {name}",
    'end.ended': "Ended {name}.",
    'end.forced': "{name} didn't close within {secs} s, so it was forced to stop.",
    'end.failed': "Couldn't end {name}: it belongs to another user or the system.",
    'end.partly': "Ended part of {name}; some of its processes belong to another user, or "
                  "are stuck waiting on a device.",
    'end.test_data': "Not sent: Spark Monitor is showing test data, not this PC.",
    'end.confirm_title': "End a system process?",
    'end.confirm': "{name} (PID {pid}) is part of the desktop or the system. Ending it can "
                   "log you out, cut the sound or freeze the screen.\n\nEnd it anyway?",
    'end.process': "End process",
    'end.tree': "End process tree",

    # Performance tab
    'perf.cpu': "CPU",
    'perf.memory': "Memory",
    'perf.gpu': "GPU {n}",
    'perf.disk': "Disk {n} ({name})",
    'perf.utilization': "Utilization",
    'perf.speed': "Speed",
    'perf.max_speed': "Max speed",
    'perf.temperature': "Temperature",
    'perf.hotspot': "Hotspot",
    'perf.threads': "Threads",
    'perf.processes': "Processes",
    'perf.uptime': "Up time",
    'perf.in_use': "In use",
    'perf.available': "Available",
    'perf.cached': "Cached",
    'perf.swap': "Swap",
    'perf.zram': "zram holds {data}, compressed to {compressed}",
    'perf.vram': "Video memory",
    'perf.gtt': "Shared memory",
    'perf.clock': "Clock",
    'perf.power': "Power",
    'perf.fan': "Fan",
    'perf.read': "Read",
    'perf.write': "Write",
    'perf.active': "Active time",
    'perf.capacity': "Capacity",
    'perf.type': "Type",
    'perf.send': "Send",
    'perf.receive': "Receive",
    'perf.link': "Link speed",
    'perf.state': "State",
    'perf.up': "Connected",
    'perf.down': "Not connected",
    'perf.per_thread': "Each thread, last 60 s",
    'perf.not_readable': "not readable",
    'perf.unreadable_gpu': "This GPU's driver doesn't publish usage in /sys.",

    # Startup tab
    'startup.on': "On",
    'startup.off': "Off",
    'startup.turn_on': "Turn on",
    'startup.turn_off': "Turn off",
    'startup.yours': "You",
    'startup.system': "System",
    'startup.app': "App",
    'startup.service': "Service",
    'startup.system_service': "Set for every user by the system; it can't be switched off "
                              "from here.",
    'startup.done_on': "{name} will start when you log in.",
    'startup.done_off': "{name} won't start when you log in.",
    'startup.failed': "Couldn't change {name}: {why}",
    'startup.empty': "Nothing starts at login.",

    # Details tab
    'state.R': "Running",
    'state.S': "Sleeping",
    'state.D': "Waiting (disk)",
    'state.Z': "Zombie",
    'state.T': "Stopped",
    'state.t': "Traced",
    'state.I': "Idle",
    'state.X': "Dead",
}

TABLES = {'en': EN}


def _table():
    for lang in languages():
        short = lang.split('_')[0].lower()
        if short in TABLES:
            return TABLES[short]
    return EN


_T = _table()


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
