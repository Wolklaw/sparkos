"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

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
    'status.crashed': "SOMETHING WENT WRONG",

    # Apps tab
    'apps.summary': "{procs} processes · {apps} apps",
    'apps.end': "End task",
    'apps.system_note': "Part of the desktop or the system. Ending it can log you out or "
                        "freeze the screen, so Spark Monitor won't from here. "
                        "Details can, if you're sure.",
    'apps.self_note': "This is Spark Monitor. Close it with the window's X.",
    'apps.not_mine': "Runs as another user. Spark Monitor can only end your own apps.",
    'apps.session': "systemd (your session)",
    'apps.login_session': "Login session",

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
    'perf.nvidia_note': "NVIDIA's driver doesn't publish usage, memory or temperature in /sys. "
                        "nvidia-smi can show them; Spark Monitor doesn't run it every second.",
    'perf.intel_note': "Intel's driver doesn't publish GPU usage in /sys; clock is shown.",
    'perf.unknown_gpu': "Unknown GPU",

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
    'startup.system_note': "Set for every user by the system.",
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

FR = {
    # tabs and headings
    'tab.apps': "Applications",
    'tab.performance': "Performances",
    'tab.startup': "Démarrage",
    'tab.details': "Détails",
    'section.app': "Applications",
    'section.background': "Arrière-plan",
    'section.system': "Système",
    'col.name': "Nom",
    'col.cpu': "Processeur",
    'col.memory': "Mémoire",
    'col.gpu': "GPU",
    'col.disk': "Disque",
    'col.pid': "PID",
    'col.user': "Utilisateur",
    'col.state': "État",
    'col.nice': "Priorité",
    'col.command': "Ligne de commande",
    'col.status': "État",
    'col.origin': "Réglé par",
    'col.about': "Description",

    # status line
    'status.watching': "EN SURVEILLANCE",
    'status.paused': "EN PAUSE PENDANT QUE C'EST CACHÉ",
    'status.test_data': "DONNÉES DE TEST",
    'status.crashed': "UN PROBLÈME EST SURVENU",

    # Apps tab
    'apps.summary': "{procs} processus · {apps} applications",
    'apps.end': "Fin de tâche",
    'apps.system_note': "Fait partie du bureau ou du système. Le fermer peut vous déconnecter "
                        "ou figer l'écran, alors Spark Monitor ne le fait pas d'ici. "
                        "L'onglet Détails le peut, si vous êtes certain.",
    'apps.self_note': "C'est Spark Monitor. Fermez-le avec le X de la fenêtre.",
    'apps.not_mine': "Tourne sous un autre utilisateur. Spark Monitor ne peut fermer que vos "
                     "propres applications.",
    'apps.session': "systemd (votre session)",
    'apps.login_session': "Session de connexion",

    # ending
    'end.ending': "FERMETURE DE {name}",
    'end.ended': "{name} est fermé.",
    'end.forced': "{name} ne s'est pas fermé en {secs} s, alors il a été arrêté de force.",
    'end.failed': "Impossible de fermer {name} : il appartient à un autre utilisateur ou au "
                  "système.",
    'end.partly': "{name} est fermé en partie; certains de ses processus appartiennent à un "
                  "autre utilisateur, ou attendent un périphérique.",
    'end.test_data': "Rien d'envoyé : Spark Monitor affiche des données de test, pas ce PC.",
    'end.confirm_title': "Fermer un processus système?",
    'end.confirm': "{name} (PID {pid}) fait partie du bureau ou du système. Le fermer peut "
                   "vous déconnecter, couper le son ou figer l'écran.\n\nLe fermer quand même?",
    'end.process': "Terminer le processus",
    'end.tree': "Terminer l'arborescence",

    # Performance tab
    'perf.cpu': "Processeur",
    'perf.memory': "Mémoire",
    'perf.gpu': "GPU {n}",
    'perf.disk': "Disque {n} ({name})",
    'perf.utilization': "Utilisation",
    'perf.speed': "Vitesse",
    'perf.max_speed': "Vitesse max.",
    'perf.temperature': "Température",
    'perf.hotspot': "Point chaud",
    'perf.threads': "Fils",
    'perf.processes': "Processus",
    'perf.uptime': "Allumé depuis",
    'perf.in_use': "Utilisée",
    'perf.available': "Disponible",
    'perf.cached': "En cache",
    'perf.swap': "Échange",
    'perf.zram': "zram contient {data}, compressé à {compressed}",
    'perf.vram': "Mémoire vidéo",
    'perf.gtt': "Mémoire partagée",
    'perf.clock': "Fréquence",
    'perf.power': "Puissance",
    'perf.fan': "Ventilateur",
    'perf.read': "Lecture",
    'perf.write': "Écriture",
    'perf.active': "Temps actif",
    'perf.capacity': "Capacité",
    'perf.type': "Type",
    'perf.send': "Envoi",
    'perf.receive': "Réception",
    'perf.link': "Vitesse du lien",
    'perf.state': "État",
    'perf.up': "Connecté",
    'perf.down': "Non connecté",
    'perf.per_thread': "Chaque fil, 60 dernières s",
    'perf.not_readable': "illisible",
    'perf.unreadable_gpu': "Le pilote de ce GPU ne publie pas son utilisation dans /sys.",
    'perf.nvidia_note': "Le pilote NVIDIA ne publie pas l'utilisation, la mémoire ni la "
                        "température dans /sys. nvidia-smi peut les montrer; Spark Monitor ne "
                        "le lance pas à chaque seconde.",
    'perf.intel_note': "Le pilote Intel ne publie pas l'utilisation du GPU dans /sys; la "
                       "fréquence est affichée.",
    'perf.unknown_gpu': "GPU inconnu",

    # Startup tab
    'startup.on': "Activé",
    'startup.off': "Désactivé",
    'startup.turn_on': "Activer",
    'startup.turn_off': "Désactiver",
    'startup.yours': "Vous",
    'startup.system': "Système",
    'startup.app': "Application",
    'startup.service': "Service",
    'startup.system_service': "Réglé pour tous les utilisateurs par le système; ne peut pas "
                              "être désactivé d'ici.",
    'startup.system_note': "Réglé pour tous les utilisateurs par le système.",
    'startup.done_on': "{name} démarrera à votre connexion.",
    'startup.done_off': "{name} ne démarrera plus à votre connexion.",
    'startup.failed': "Impossible de modifier {name} : {why}",
    'startup.empty': "Rien ne démarre à la connexion.",

    # Details tab
    'state.R': "En cours",
    'state.S': "En veille",
    'state.D': "En attente (disque)",
    'state.Z': "Zombie",
    'state.T': "Arrêté",
    'state.t': "Tracé",
    'state.I': "Inactif",
    'state.X': "Mort",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
