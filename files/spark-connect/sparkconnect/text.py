"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import local_units, ui_language

EN = {
    # header and status
    'status.watching': "WATCHING {n} MACHINES",
    'status.watching_one': "WATCHING 1 MACHINE",
    'status.refreshing': "REFRESHING",
    'status.paused': "PAUSED WHILE HIDDEN",
    'status.no_config': "NO MACHINES YET",
    'status.config_error': "MACHINE LIST HAS AN ERROR",
    'status.crashed': "SOMETHING WENT WRONG",
    'status.restarted': "RESTARTED {unit} ON {machine}",
    'status.copied': "REPORT COPIED",

    # overview
    'overview.machines': "Machines",
    'overview.sites': "Websites",
    'overview.no_sites': "No websites in the machine list.",
    'overview.empty_title': "No machines yet",
    'overview.empty_body': "Spark Connect reads its machine list from\n{path}\n\nThat file "
                           "doesn't exist yet. Copy machines.example.toml from\n{example}\n"
                           "there, put in your own machines, and press F5. Spark Connect "
                           "never writes that file.",
    'overview.error_title': "The machine list has an error",
    'overview.error_body': "{error}\n\nIn {path}. Fix it and press F5.",
    'card.up': "UP",
    'card.down': "DOWN",
    'card.trouble': "TROUBLE",
    'card.waiting': "WAITING",
    'card.uptime': "UP FOR",
    'card.load': "LOAD",
    'card.memory': "MEMORY",
    'card.disk': "DISK",
    'card.temp': "TEMP",
    'card.more': "+{n} more",
    'site.checking': "checking",
    'widget.all_good': "All good",
    'widget.trouble': "{n} need a look",
    'widget.checked': "Checked at {time}",
    'widget.open': "Open Spark Connect",
    'widget.no_answer': "no answer",

    # verdicts
    'verdict.ok': "All good",
    'verdict.waiting': "Waiting for the first refresh",
    'verdict.unreachable': "Unreachable since {since}",
    'verdict.hostkey_changed': "Host key changed: check it before connecting",
    'verdict.hostkey_unknown': "Host key not known yet: connect once in a terminal",
    'verdict.auth': "SSH key not accepted",
    'verdict.bad_output': "The probe's answer couldn't be read",
    'verdict.no_ssh': "ssh is not installed on this PC",
    'verdict.error': "SSH failed: {message}",
    'verdict.no_systemd': "No systemd: services can't be read",
    'verdict.unit_failed': "{unit} failed",
    'verdict.units_failed': "{n} units failed",
    'verdict.unit_restarting': "{unit} restarting",
    'verdict.unit_stopped': "{unit} stopped",
    'verdict.unit_missing': "{unit} not found",
    'verdict.tunnel_down': "Tunnel down ({unit} not running)",
    'verdict.tunnel_reconnecting': "{unit} reconnecting (no connections)",
    'verdict.taken_over': "Standby has taken over: it is serving the sites",
    'verdict.failover_missing': "Failover folder not found",
    'verdict.disk_full': "Disk {pct} full ({mount})",
    'verdict.memory_low': "Memory nearly full ({pct} free)",
    'verdict.hot': "Running hot: {c}",
    'verdict.check_failed': "Health check {name}: {why}",
    'verdict.reboot_kernel': "Reboot needed: kernel update waiting since {day}",
    'verdict.reboot_pkgs': "Reboot needed for {pkgs}, waiting since {day}",
    'verdict.reboot_needed': "Reboot needed, waiting since {day}",
    'verdict.rebooting': "Rebooting (sent at {since})",
    'health.updates': "Updates",
    'health.updates_n': "{n} waiting, {security} security",
    'health.updates_none': "up to date",
    'health.reboot': "Reboot",
    'health.reboot_needed': "needed since {day} ({pkgs})",

    # machine view
    'tab.services': "Services",
    'tab.health': "Health",
    'tab.tunnel': "Tunnel",
    'tab.failover': "Failover",
    'tab.logs': "Logs",
    'machine.refreshed': "REFRESHED {time}",
    'machine.no_data': "No data from this machine yet.",
    'machine.ssh_said': "ssh said: {message}",
    'machine.fingerprint': "Host key ssh was shown: {fp}",
    'machine.hostkey_help': "Spark Connect never accepts a host key. Open a terminal, check "
                            "the key against the server's own (ssh-keygen -lf on the server), "
                            "and accept it there yourself if it is right.",
    'services.watched': "Watched units",
    'services.other_failed': "Other failed units",
    'services.known_failed': "known failed, ignored",
    'services.none': "No units listed for this machine in the config.",
    'services.for': "for {time}",
    'services.restarts': "{n} restarts",
    'services.no_log': "no log lines (the journal may need the adm group to read)",
    'state.running': "RUNNING",
    'state.failed': "FAILED",
    'state.restarting': "RESTARTING",
    'state.stopped': "STOPPED",
    'state.missing': "NOT FOUND",
    'state.unknown': "UNKNOWN",
    'scope.system': "SYSTEM",
    'scope.user': "USER",
    'health.os': "System",
    'health.cpu': "CPU",
    'health.load': "Load",
    'health.memory': "Memory",
    'health.swap': "Swap",
    'health.disks': "Disks",
    'health.temps': "Temperatures",
    'health.network': "Network",
    'health.boot': "Last reboot",
    'health.uptime': "Up for",
    'health.cpus': "{n} CPUs",
    'health.used_of': "{used} used of {total}",
    'health.free_of': "{pct} full, {free} free of {total}",
    'health.rx_tx': "in {rx} · out {tx}",
    'health.rate_next': "rate after the next refresh",
    'tunnel.none': "No tunnel set for this machine in the config.",
    'tunnel.state': "State",
    'tunnel.connections': "Connections",
    'tunnel.hostnames': "Sites behind it",
    'tunnel.connected': "CONNECTED",
    'tunnel.no_conns': "NO CONNECTIONS",
    'tunnel.down': "NOT RUNNING",
    'tunnel.conns_unknown': "unknown (ss can't see it)",
    'tunnel.no_hostnames': "none listed in the config",
    'failover.standing_by': "STANDING BY",
    'failover.taken_over': "TAKEN OVER",
    'failover.taken_over_note': "This machine is serving the sites. It stays live until "
                                "someone runs the failback.",
    'failover.standing_by_note': "The main server is serving the sites.",
    'failover.unknown': "Can't tell: no active_unit in the config.",
    'failover.incidents': "Last incidents",
    'failover.no_incidents': "No incident files.",
    'failover.netmon': "Network monitor, last lines",
    'failover.no_netmon': "No network monitor log set in the config, or it isn't there.",
    'failover.failback': "Failback command",
    'failover.no_failback': "No failback command in the config.",
    'logs.unit': "Unit",
    'logs.filter': "Filter",
    'logs.start': "Follow",
    'logs.stop': "Stop",
    'logs.pick': "Pick a unit to follow its journal live.",
    'logs.following': "FOLLOWING {unit}",

    # actions
    'action.back': "Overview",
    'action.terminal': "Open terminal",
    'action.report': "Copy report",
    'action.refresh': "Refresh",
    'action.restart': "Restart",
    'action.logs': "Logs",
    'action.failback': "Failback…",
    'action.failback_open': "Open terminal",
    'action.cancel': "Cancel",
    'action.update': "Update…",
    'action.update_open': "Open terminal",
    'action.reboot': "Reboot",
    'action.reboot_menu': "Reboot…",
    'confirm.restart_title': "Restart {unit} on {machine}?",
    'confirm.restart_body': "This restarts {unit} on {machine}. It stops for a moment and "
                            "starts again.",
    'confirm.runs': "Runs: {command}",
    'confirm.touches_unit': "Touches: only {unit}. Nothing else is stopped or changed.",
    'confirm.tunnel_sites': "Every site behind this tunnel drops for a few seconds: {sites}",
    'confirm.tunnel_unlisted': "Every site behind this tunnel drops for a few seconds. The "
                               "config doesn't list them (tunnel_hostnames).",
    'confirm.sudo': "A system unit goes through sudo -n: if sudo asks for a password, nothing "
                    "runs and Spark Connect offers a terminal instead. It never asks for, "
                    "types or stores a password.",
    'confirm.terminal_title': "Open a terminal on {machine}?",
    'confirm.terminal_body': "Opens a terminal window logged in to {machine}.",
    'confirm.terminal_touches': "Touches: nothing by itself. What you type there runs on "
                                "the server.",
    'confirm.failback_title': "Fail back from {machine}?",
    'confirm.failback_body': "Opens a terminal on the standby with the failback command typed "
                             "but not run. Press Enter there to run it, or Ctrl+C to drop it.",
    'confirm.typed': "Typed, not run: {command}\nOn: {machine}",
    'confirm.failback_touches': "Touches: the failback script decides; usually it hands the "
                                "sites back to the main server and stops the standby's "
                                "tunnel.",
    'result.restarted': "Restarted {unit} on {machine}.",
    'result.needs_password_title': "sudo wants a password",
    'result.needs_password': "sudo on {machine} asks for a password to restart {unit}, so "
                             "nothing ran. Spark Connect doesn't type passwords. Open a "
                             "terminal and run it there?",
    'result.failed_title': "Restart failed",
    'result.failed': "Restarting {unit} on {machine} didn't work:\n{message}",
    'result.no_terminal': "No terminal program found (Spark Terminal, Konsole, xterm…).",
    'result.no_terminal_title': "No terminal",
    'confirm.update_title': "Update {machine}?",
    'confirm.update_body': "Opens a terminal on {machine} and installs the waiting updates. The "
                           "package manager lists them and asks before it changes anything.",
    'confirm.update_count': "Waiting: {n} updates, {security} of them security.",
    'confirm.update_touches': "Touches: the system packages. Services whose packages change "
                              "restart on their own. Leave the window open until it finishes; "
                              "sudo may ask for your password there.",
    'confirm.reboot_title': "Reboot {machine}?",
    'confirm.reboot_body': "This restarts the whole machine. Everything on {machine} stops "
                           "until it is back, usually a minute or two.",
    'confirm.reboot_sites': "These sites are down until it is back: {sites}",
    'confirm.reboot_touches': "Touches: every service on {machine}.",
    'confirm.reboot_standby': "{standby} watches {machine} and may take over while it is down. "
                              "Once {machine} is back, use Failback on {standby} to hand the "
                              "sites back.",
    'confirm.reboot_sudo': "Goes through sudo -n: if sudo asks for a password, nothing runs and "
                           "Spark Connect offers a terminal instead.",
    'result.reboot_password': "sudo on {machine} asks for a password to reboot, so nothing "
                              "ran. Spark Connect doesn't type passwords. Open a terminal to "
                              "do it?",
    'result.reboot_failed_title': "Reboot failed",
    'result.reboot_failed': "Rebooting {machine} didn't work:\n{message}",
    'status.rebooting': "REBOOTING {machine}",

    # console (servers with no desktop)
    'action.console': "See console",
    'action.console_open': "See console",
    'confirm.console_title': "See the console of {machine}?",
    'confirm.console_body': "Opens a terminal that shows what {machine} has on its own screen "
                            "(the text console, tty1). You can switch to typing into it with "
                            "Ctrl+], and back with Ctrl+]. Q or Ctrl+C closes it.",
    'confirm.console_note': "This always uses sudo: reading the console needs root, so you type "
                            "the sudo password of {machine} in that terminal. There is no prompt "
                            "for anybody at {machine} to answer. While it runs, a one-line "
                            "notice on tty1 says which PC is viewing, and another says when it "
                            "ends.",
    'confirm.console_touches': "Touches: nothing is installed on {machine}. A short Python "
                               "script runs there as root until you close the terminal. Typing "
                               "uses a virtual keyboard (/dev/uinput) and assumes a US layout.",
    'desktop.console': "NO DESKTOP: CONSOLE ONLY",

    # screen sharing (desktop machines)
    'action.take_control': "Take control",
    'action.take_control_sudo': "Take control without asking…",
    'action.stop': "Stop",
    'action.share_open': "Take control",
    'action.share_sudo_open': "Take control",
    'desktop.in_use': "DESKTOP IN USE",
    'desktop.in_use_user': "DESKTOP IN USE ({user})",
    'desktop.locked': "DESKTOP LOCKED",
    'desktop.none': "NOBODY LOGGED IN",
    'desktop.no_tool': "spark-share isn't installed here yet",
    'desktop.locked_note': "The screen is locked, so nobody can answer the prompt. Take "
                           "control without asking still works.",
    'desktop.none_note': "Nobody is logged in to a graphical session on this machine.",
    'card.sharing': "SCREEN SHARED, {m} MIN",
    'status.sharing': "SHARING {machine}",
    'status.share_ended': "SCREEN SHARE WITH {machine} ENDED",
    'confirm.share_title': "Take control of {machine}'s screen?",
    'confirm.share_body': "You will see and control the screen of {machine} in a FreeRDP "
                          "window until you press Stop. This version can't show the screen "
                          "without also giving control.",
    'confirm.share_prompt': "The person at {machine} sees a prompt on their screen saying who "
                            "is asking and from which PC. Nothing is shared until they press "
                            "Allow; no answer in 30 seconds counts as Deny. Once it runs, "
                            "their screen shows a banner with a Stop button.",
    'confirm.share_touches': "Touches: nothing is installed. A one-time screen server runs on "
                             "{machine} for this session, reachable only through an SSH "
                             "forward on 127.0.0.1.",
    'confirm.share_sudo_title': "Take control of {machine} without asking?",
    'confirm.share_sudo_body': "Skips the prompt: nobody at {machine} is asked first. Their "
                               "screen shows a banner with a Stop button the whole time, but "
                               "the share starts without their say. Use it on your own "
                               "machines, or when you have told them.",
    'confirm.share_sudo_note': "Goes through sudo -n. If sudo asks for a password, nothing "
                               "runs and Spark Connect offers a terminal where you type it "
                               "yourself. It never types or stores a password.",
    'share.password_title': "sudo wants a password",
    'share.password': "sudo on {machine} asks for a password, so nothing ran. Spark Connect "
                      "doesn't type passwords. Open a terminal there: type the password in "
                      "it, and the screen opens here once sudo accepts. Closing that "
                      "terminal ends the share.",
    'share.denied_title': "Not shared",
    'share.failed_title': "Screen share failed",
    'share.failed': "Couldn't take control of {machine}:\n{message}",
    'share.err.denied': "The person at the screen didn't allow it, or didn't answer in 30 "
                        "seconds.",
    'share.err.locked': "The screen is locked, so nobody can answer the prompt. Use Take "
                        "control without asking, or unlock it first.",
    'share.err.no_session': "Nobody is logged in to a graphical session on {machine}.",
    'share.err.other_user': "The graphical session on {machine} belongs to another user, so "
                            "only Take control without asking (sudo) can reach it.",
    'share.err.no_rdp': "{machine} has no spark-rdp (Spark's screen sharing server), so it "
                        "can't share its screen. Update that machine first.",
    'share.err.no_krdp': "{machine} has no krdpserver (KDE's RDP server), so it can't share "
                         "its screen.",
    'share.err.no_tool': "{machine} doesn't have spark-share yet. It comes with the SparkOS "
                         "image; update that machine first.",
    'share.err.no_viewer': "FreeRDP isn't installed on this PC, so there is nothing to show "
                           "the screen with.",
    'share.err.forward': "The SSH forward to {machine} didn't open.",
    'share.err.timeout': "{machine} didn't answer in time.",
    'share.err.no_terminal': "No terminal program found (Spark Terminal, Konsole, xterm…).",
    'share.err.bad_reply': "spark-share on {machine} answered in a way Spark Connect doesn't "
                           "understand. Update both.",
    'share.err.ssh': "ssh said: {message}",
    'share.err.error': "{message}",
    'result.update_unknown_title': "No package manager yet",
    'result.update_unknown': "Spark Connect doesn't know {machine}'s package manager yet (apt "
                             "or dnf). Wait for a refresh, or update it from a terminal.",

    # alerts
    'alert.back': "Back to normal: {text}",
}

FR = {
    'status.watching': "{n} MACHINES SURVEILLÉES",
    'status.watching_one': "1 MACHINE SURVEILLÉE",
    'status.refreshing': "ACTUALISATION",
    'status.paused': "EN PAUSE (FENÊTRE CACHÉE)",
    'status.no_config': "AUCUNE MACHINE",
    'status.config_error': "ERREUR DANS LA LISTE",
    'status.crashed': "QUELQUE CHOSE A MAL TOURNÉ",
    'status.restarted': "{unit} REDÉMARRÉ SUR {machine}",
    'status.copied': "RAPPORT COPIÉ",

    'overview.machines': "Machines",
    'overview.sites': "Sites web",
    'overview.no_sites': "Aucun site dans la liste des machines.",
    'overview.empty_title': "Aucune machine",
    'overview.empty_body': "Spark Connect lit sa liste de machines dans\n{path}\n\nCe "
                           "fichier n'existe pas encore. Copiez-y machines.example.toml de\n"
                           "{example}\nmettez-y vos machines, puis appuyez sur F5. Spark "
                           "Connect n'écrit jamais ce fichier.",
    'overview.error_title': "La liste des machines a une erreur",
    'overview.error_body': "{error}\n\nDans {path}. Corrigez-la et appuyez sur F5.",
    'card.up': "EN LIGNE",
    'card.down': "HORS LIGNE",
    'card.trouble': "PROBLÈME",
    'card.waiting': "EN ATTENTE",
    'card.uptime': "EN MARCHE",
    'card.load': "CHARGE",
    'card.memory': "MÉMOIRE",
    'card.disk': "DISQUE",
    'card.temp': "TEMP.",
    'card.more': "+{n} autres",
    'site.checking': "vérification",
    'widget.all_good': "Tout va bien",
    'widget.trouble': "{n} à vérifier",
    'widget.checked': "Vérifié à {time}",
    'widget.open': "Ouvrir Spark Connect",
    'widget.no_answer': "pas de réponse",

    'verdict.ok': "Tout va bien",
    'verdict.waiting': "En attente de la première lecture",
    'verdict.unreachable': "Injoignable depuis {since}",
    'verdict.hostkey_changed': "Clé d'hôte changée : vérifiez-la avant de vous connecter",
    'verdict.hostkey_unknown': "Clé d'hôte inconnue : connectez-vous une fois dans un terminal",
    'verdict.auth': "Clé SSH refusée",
    'verdict.bad_output': "La réponse de la sonde est illisible",
    'verdict.no_ssh': "ssh n'est pas installé sur ce PC",
    'verdict.error': "Échec SSH : {message}",
    'verdict.no_systemd': "Pas de systemd : services illisibles",
    'verdict.unit_failed': "{unit} en échec",
    'verdict.units_failed': "{n} unités en échec",
    'verdict.unit_restarting': "{unit} redémarre",
    'verdict.unit_stopped': "{unit} arrêté",
    'verdict.unit_missing': "{unit} introuvable",
    'verdict.tunnel_down': "Tunnel coupé ({unit} arrêté)",
    'verdict.tunnel_reconnecting': "{unit} se reconnecte (aucune connexion)",
    'verdict.taken_over': "La machine de secours a pris le relais : elle sert les sites",
    'verdict.failover_missing': "Dossier de bascule introuvable",
    'verdict.disk_full': "Disque plein à {pct} ({mount})",
    'verdict.memory_low': "Mémoire presque pleine ({pct} libre)",
    'verdict.hot': "Température élevée : {c}",
    'verdict.check_failed': "Vérification {name} : {why}",
    'verdict.reboot_kernel': "Redémarrage requis : noyau mis à jour, en attente depuis le {day}",
    'verdict.reboot_pkgs': "Redémarrage requis pour {pkgs}, en attente depuis le {day}",
    'verdict.reboot_needed': "Redémarrage requis, en attente depuis le {day}",
    'verdict.rebooting': "Redémarrage (envoyé à {since})",
    'health.updates': "Mises à jour",
    'health.updates_n': "{n} en attente, {security} de sécurité",
    'health.updates_none': "à jour",
    'health.reboot': "Redémarrage",
    'health.reboot_needed': "requis depuis le {day} ({pkgs})",

    'tab.services': "Services",
    'tab.health': "État",
    'tab.tunnel': "Tunnel",
    'tab.failover': "Bascule",
    'tab.logs': "Journaux",
    'machine.refreshed': "LU À {time}",
    'machine.no_data': "Aucune donnée de cette machine pour l'instant.",
    'machine.ssh_said': "ssh a répondu : {message}",
    'machine.fingerprint': "Clé d'hôte montrée par ssh : {fp}",
    'machine.hostkey_help': "Spark Connect n'accepte jamais une clé d'hôte. Ouvrez un "
                            "terminal, comparez la clé avec celle du serveur (ssh-keygen -lf "
                            "sur le serveur) et acceptez-la vous-même si elle est bonne.",
    'services.watched': "Unités surveillées",
    'services.other_failed': "Autres unités en échec",
    'services.known_failed': "échec connu, ignoré",
    'services.none': "Aucune unité listée pour cette machine dans la configuration.",
    'services.for': "depuis {time}",
    'services.restarts': "{n} redémarrages",
    'services.no_log': "aucune ligne de journal (lire le journal peut demander le groupe adm)",
    'state.running': "EN MARCHE",
    'state.failed': "EN ÉCHEC",
    'state.restarting': "REDÉMARRE",
    'state.stopped': "ARRÊTÉ",
    'state.missing': "INTROUVABLE",
    'state.unknown': "INCONNU",
    'scope.system': "SYSTÈME",
    'scope.user': "UTILISATEUR",
    'health.os': "Système",
    'health.cpu': "Processeur",
    'health.load': "Charge",
    'health.memory': "Mémoire",
    'health.swap': "Swap",
    'health.disks': "Disques",
    'health.temps': "Températures",
    'health.network': "Réseau",
    'health.boot': "Dernier démarrage",
    'health.uptime': "En marche depuis",
    'health.cpus': "{n} processeurs",
    'health.used_of': "{used} utilisés sur {total}",
    'health.free_of': "plein à {pct}, {free} libres sur {total}",
    'health.rx_tx': "entrée {rx} · sortie {tx}",
    'health.rate_next': "débit à la prochaine lecture",
    'tunnel.none': "Aucun tunnel pour cette machine dans la configuration.",
    'tunnel.state': "État",
    'tunnel.connections': "Connexions",
    'tunnel.hostnames': "Sites derrière",
    'tunnel.connected': "CONNECTÉ",
    'tunnel.no_conns': "AUCUNE CONNEXION",
    'tunnel.down': "ARRÊTÉ",
    'tunnel.conns_unknown': "inconnu (ss ne le voit pas)",
    'tunnel.no_hostnames': "aucun dans la configuration",
    'failover.standing_by': "EN ATTENTE",
    'failover.taken_over': "RELAIS PRIS",
    'failover.taken_over_note': "Cette machine sert les sites. Elle le reste jusqu'à ce que "
                                "quelqu'un lance le retour (failback).",
    'failover.standing_by_note': "Le serveur principal sert les sites.",
    'failover.unknown': "Impossible à dire : pas d'active_unit dans la configuration.",
    'failover.incidents': "Derniers incidents",
    'failover.no_incidents': "Aucun fichier d'incident.",
    'failover.netmon': "Moniteur réseau, dernières lignes",
    'failover.no_netmon': "Pas de journal du moniteur réseau dans la configuration, ou "
                          "introuvable.",
    'failover.failback': "Commande de retour",
    'failover.no_failback': "Aucune commande de retour dans la configuration.",
    'logs.unit': "Unité",
    'logs.filter': "Filtre",
    'logs.start': "Suivre",
    'logs.stop': "Arrêter",
    'logs.pick': "Choisissez une unité pour suivre son journal en direct.",
    'logs.following': "SUIVI DE {unit}",

    'action.back': "Vue d'ensemble",
    'action.terminal': "Ouvrir un terminal",
    'action.report': "Copier le rapport",
    'action.refresh': "Actualiser",
    'action.restart': "Redémarrer",
    'action.logs': "Journal",
    'action.failback': "Retour…",
    'action.failback_open': "Ouvrir le terminal",
    'action.cancel': "Annuler",
    'action.update': "Mettre à jour…",
    'action.update_open': "Ouvrir le terminal",
    'action.reboot': "Redémarrer",
    'action.reboot_menu': "Redémarrer…",
    'confirm.restart_title': "Redémarrer {unit} sur {machine} ?",
    'confirm.restart_body': "Ceci redémarre {unit} sur {machine}. Il s'arrête un instant puis "
                            "repart.",
    'confirm.runs': "Lance : {command}",
    'confirm.touches_unit': "Touche : seulement {unit}. Rien d'autre n'est arrêté ni modifié.",
    'confirm.tunnel_sites': "Chaque site derrière ce tunnel tombe quelques secondes : {sites}",
    'confirm.tunnel_unlisted': "Chaque site derrière ce tunnel tombe quelques secondes. La "
                               "configuration ne les liste pas (tunnel_hostnames).",
    'confirm.sudo': "Une unité système passe par sudo -n : si sudo demande un mot de passe, "
                    "rien n'est lancé et Spark Connect propose un terminal. Il ne demande, ne "
                    "tape et ne garde jamais de mot de passe.",
    'confirm.terminal_title': "Ouvrir un terminal sur {machine} ?",
    'confirm.terminal_body': "Ouvre une fenêtre de terminal connectée à {machine}.",
    'confirm.terminal_touches': "Touche : rien en soi. Ce que vous y tapez s'exécute sur le "
                                "serveur.",
    'confirm.failback_title': "Revenir depuis {machine} ?",
    'confirm.failback_body': "Ouvre un terminal sur la machine de secours avec la commande de "
                             "retour tapée mais pas lancée. Appuyez sur Entrée pour la lancer, "
                             "ou Ctrl+C pour l'abandonner.",
    'confirm.typed': "Tapée, pas lancée : {command}\nSur : {machine}",
    'confirm.failback_touches': "Touche : ce que fait le script de retour ; d'habitude il "
                                "rend les sites au serveur principal et arrête le tunnel de "
                                "secours.",
    'result.restarted': "{unit} redémarré sur {machine}.",
    'result.needs_password_title': "sudo demande un mot de passe",
    'result.needs_password': "sudo sur {machine} demande un mot de passe pour redémarrer "
                             "{unit}, donc rien n'a été lancé. Spark Connect ne tape pas de "
                             "mot de passe. Ouvrir un terminal pour le faire ?",
    'result.failed_title': "Le redémarrage a échoué",
    'result.failed': "Le redémarrage de {unit} sur {machine} n'a pas marché :\n{message}",
    'result.no_terminal': "Aucun terminal trouvé (Spark Terminal, Konsole, xterm…).",
    'result.no_terminal_title': "Pas de terminal",
    'confirm.update_title': "Mettre à jour {machine} ?",
    'confirm.update_body': "Ouvre un terminal sur {machine} et installe les mises à jour en "
                           "attente. Le gestionnaire de paquets les liste et demande avant de "
                           "changer quoi que ce soit.",
    'confirm.update_count': "En attente : {n} mises à jour, dont {security} de sécurité.",
    'confirm.update_touches': "Touche : les paquets du système. Les services dont les paquets "
                              "changent redémarrent d'eux-mêmes. Laissez la fenêtre ouverte "
                              "jusqu'à la fin ; sudo peut y demander votre mot de passe.",
    'confirm.reboot_title': "Redémarrer {machine} ?",
    'confirm.reboot_body': "Ceci redémarre toute la machine. Tout s'arrête sur {machine} "
                           "jusqu'à son retour, d'habitude une minute ou deux.",
    'confirm.reboot_sites': "Ces sites sont coupés jusqu'à son retour : {sites}",
    'confirm.reboot_touches': "Touche : tous les services de {machine}.",
    'confirm.reboot_standby': "{standby} surveille {machine} et peut prendre le relais pendant "
                              "la coupure. Au retour de {machine}, utilisez Retour sur "
                              "{standby} pour lui rendre les sites.",
    'confirm.reboot_sudo': "Passe par sudo -n : si sudo demande un mot de passe, rien n'est "
                           "lancé et Spark Connect propose un terminal.",
    'result.reboot_password': "sudo sur {machine} demande un mot de passe pour redémarrer, "
                              "donc rien n'a été lancé. Spark Connect ne tape pas de mot de "
                              "passe. Ouvrir un terminal pour le faire ?",
    'result.reboot_failed_title': "Le redémarrage a échoué",
    'result.reboot_failed': "Le redémarrage de {machine} n'a pas marché :\n{message}",
    'status.rebooting': "{machine} REDÉMARRE",

    # console (serveurs sans bureau)
    'action.console': "Voir la console",
    'action.console_open': "Voir la console",
    'confirm.console_title': "Voir la console de {machine} ?",
    'confirm.console_body': "Ouvre un terminal qui montre ce que {machine} affiche sur son "
                            "propre écran (la console texte, tty1). Ctrl+] passe à la saisie "
                            "dans la console, et y revient. Q ou Ctrl+C le ferme.",
    'confirm.console_note': "Cela passe toujours par sudo : lire la console demande root, donc "
                            "vous tapez le mot de passe sudo de {machine} dans ce terminal. "
                            "Aucune demande n'est posée à qui que ce soit devant {machine}. "
                            "Pendant l'affichage, une ligne sur tty1 indique quel PC regarde, "
                            "et une autre indique la fin.",
    'confirm.console_touches': "Touche : rien n'est installé sur {machine}. Un court script "
                               "Python s'y exécute en root jusqu'à la fermeture du terminal. "
                               "La saisie passe par un clavier virtuel (/dev/uinput) et suppose "
                               "une disposition US.",
    'desktop.console': "SANS BUREAU : CONSOLE SEULEMENT",

    # partage d'écran (machines avec un bureau)
    'action.take_control': "Prendre le contrôle",
    'action.take_control_sudo': "Prendre le contrôle sans demander…",
    'action.stop': "Arrêter",
    'action.share_open': "Prendre le contrôle",
    'action.share_sudo_open': "Prendre le contrôle",
    'desktop.in_use': "BUREAU UTILISÉ",
    'desktop.in_use_user': "BUREAU UTILISÉ ({user})",
    'desktop.locked': "BUREAU VERROUILLÉ",
    'desktop.none': "PERSONNE DE CONNECTÉ",
    'desktop.no_tool': "spark-share n'est pas encore installé ici",
    'desktop.locked_note': "L'écran est verrouillé : personne ne peut répondre à la demande. "
                           "Prendre le contrôle sans demander fonctionne quand même.",
    'desktop.none_note': "Personne n'est connecté à une session graphique sur cette machine.",
    'card.sharing': "ÉCRAN PARTAGÉ, {m} MIN",
    'status.sharing': "PARTAGE DE {machine}",
    'status.share_ended': "PARTAGE D'ÉCRAN AVEC {machine} TERMINÉ",
    'confirm.share_title': "Prendre le contrôle de l'écran de {machine} ?",
    'confirm.share_body': "Vous verrez et contrôlerez l'écran de {machine} dans une fenêtre "
                          "FreeRDP jusqu'à ce que vous appuyiez sur Arrêter. Cette version "
                          "ne peut pas montrer l'écran sans donner aussi le contrôle.",
    'confirm.share_prompt': "La personne devant {machine} voit une demande à l'écran qui dit "
                            "qui demande et depuis quel PC. Rien n'est partagé tant qu'elle "
                            "n'a pas appuyé sur Autoriser ; sans réponse en 30 secondes, "
                            "c'est un refus. Une fois le partage lancé, son écran affiche un "
                            "bandeau avec un bouton Arrêter.",
    'confirm.share_touches': "Touche : rien n'est installé. Un serveur d'écran à usage unique "
                             "tourne sur {machine} pendant cette session, joignable "
                             "seulement par une redirection SSH sur 127.0.0.1.",
    'confirm.share_sudo_title': "Prendre le contrôle de {machine} sans demander ?",
    'confirm.share_sudo_body': "Saute la demande : personne devant {machine} n'est consulté. "
                               "Son écran affiche un bandeau avec un bouton Arrêter pendant "
                               "tout le partage, mais le partage commence sans son accord. "
                               "À utiliser sur vos propres machines, ou après l'avoir "
                               "prévenue.",
    'confirm.share_sudo_note': "Passe par sudo -n. Si sudo demande un mot de passe, rien ne "
                               "s'exécute et Spark Connect propose un terminal où vous le "
                               "tapez vous-même. Il ne tape ni ne garde jamais de mot de "
                               "passe.",
    'share.password_title': "sudo demande un mot de passe",
    'share.password': "sudo sur {machine} demande un mot de passe, donc rien ne s'est "
                      "exécuté. Spark Connect ne tape pas de mots de passe. Ouvrez un "
                      "terminal : tapez-y le mot de passe, et l'écran s'ouvre ici dès que "
                      "sudo accepte. Fermer ce terminal met fin au partage.",
    'share.denied_title': "Pas partagé",
    'share.failed_title': "Le partage d'écran a échoué",
    'share.failed': "Impossible de prendre le contrôle de {machine} :\n{message}",
    'share.err.denied': "La personne devant l'écran n'a pas autorisé, ou n'a pas répondu en "
                        "30 secondes.",
    'share.err.locked': "L'écran est verrouillé : personne ne peut répondre à la demande. "
                        "Utilisez Prendre le contrôle sans demander, ou déverrouillez "
                        "d'abord.",
    'share.err.no_session': "Personne n'est connecté à une session graphique sur {machine}.",
    'share.err.other_user': "La session graphique de {machine} appartient à un autre "
                            "utilisateur : seul Prendre le contrôle sans demander (sudo) "
                            "peut l'atteindre.",
    'share.err.no_rdp': "{machine} n'a pas spark-rdp (le serveur de partage d'écran de "
                        "Spark) : elle ne peut pas partager son écran. Mettez d'abord cette "
                        "machine à jour.",
    'share.err.no_krdp': "{machine} n'a pas krdpserver (le serveur RDP de KDE) : elle ne peut "
                         "pas partager son écran.",
    'share.err.no_tool': "{machine} n'a pas encore spark-share. Il arrive avec l'image "
                         "SparkOS ; mettez d'abord cette machine à jour.",
    'share.err.no_viewer': "FreeRDP n'est pas installé sur ce PC : rien pour afficher "
                           "l'écran.",
    'share.err.forward': "La redirection SSH vers {machine} ne s'est pas ouverte.",
    'share.err.timeout': "{machine} n'a pas répondu à temps.",
    'share.err.no_terminal': "Aucun terminal trouvé (Spark Terminal, Konsole, xterm…).",
    'share.err.bad_reply': "spark-share sur {machine} a répondu d'une façon que Spark "
                           "Connect ne comprend pas. Mettez les deux à jour.",
    'share.err.ssh': "ssh a dit : {message}",
    'share.err.error': "{message}",
    'result.update_unknown_title': "Gestionnaire de paquets inconnu",
    'result.update_unknown': "Spark Connect ne connaît pas encore le gestionnaire de paquets de "
                             "{machine} (apt ou dnf). Attendez une actualisation, ou faites la "
                             "mise à jour dans un terminal.",

    'alert.back': "Revenu à la normale : {text}",
}

_TABLE = FR if ui_language() == 'fr' else EN


def t(key: str, **kw) -> str:
    text = _TABLE.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text


def verdict_text(problem) -> str:
    """The sentence for a probe.Problem, numbers written the PC's way."""
    from . import core
    args = dict(problem.args)
    if 'since' in args:
        args['since'] = core.clock(args['since'])
    if 'pct' in args:
        args['pct'] = core.pct(args['pct'])
    if 'c' in args:
        args['c'] = core.temp(args['c'])
    if 'day' in args:
        args['day'] = core.date(args['day'])
    return local_units(t('verdict.' + problem.key, **args))
