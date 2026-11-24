"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    'tab.overview': "Overview",
    'tab.rules': "Rules",
    'tab.ports': "Ports",

    'status.watching': "WATCHING",
    'status.crashed': "SOMETHING WENT WRONG",
    'status.applying': "WAITING FOR PASSWORD",
    'status.starting': "TURNING ON",
    'status.stopping': "TURNING OFF",
    'status.done': "DONE",
    'status.failed': "FAILED",
    'status.cancelled': "CANCELLED",

    'apply.apply': "Apply",
    'apply.revert': "Revert",
    'apply.waiting': "{n} change(s) not applied yet. Apply asks for your password once.",
    'apply.cancelled': "The password prompt was cancelled.",

    'yes': "Yes",
    'no': "No",
    'tile.state': "Firewall",
    'tile.boot': "Starts at boot",
    'tile.default': "Default zone",
    'tile.open': "Open in this zone",
    'state.on': "ON",
    'state.off': "OFF",
    'state.missing': "NOT INSTALLED",

    'power.off': "Turn off",
    'power.confirm': "Click again to turn off",
    'power.on': "Turn on",
    'power.on_note': "While it is on, other computers can only reach what the zone allows.",
    'power.off_note': "While it is off, every program on this PC that listens for connections "
                      "can be reached from the network.",
    'power.missing': "firewalld is not installed on this system, so there is nothing to control.",

    'hint.stopped': "The firewall is off. Nothing is blocked, and rules can't be changed until "
                    "it is turned on.",
    'hint.wide': "The zone {zone} already allows every port from 1025 to 65535, so a rule for a "
                 "port in that range changes nothing here. A zone such as public only opens "
                 "what is listed. Change the zone of your network on the Overview.",
    'hint.failed': "The last change failed: {error}",

    'net.heading': "Connected networks",
    'net.none': "No network connection was found.",
    'net.zone_for': "Zone for {name}",
    'net.zone_changing': "{zone} (not applied)",
    'col.network': "Network",
    'col.device': "Device",
    'col.zone': "Zone",
    'col.kind': "Type",
    'col.what': "Service",
    'col.ports': "Ports",
    'col.state': "State",

    'default.heading': "Zone for new networks",
    'default.note': "A network you haven't picked a zone for uses this one.",

    'zone.other': "A zone you or the system added.",
    'zone.public': "Public: for networks you don't know, like a café. Only the listed rules are open.",
    'zone.home': "Home: a network you trust. Finding devices and sharing are allowed.",
    'zone.work': "Work: a network at work. Like Home, with fewer shortcuts.",
    'zone.internal': "Internal: your own network behind a router.",
    'zone.trusted': "Trusted: everything is allowed in. Use it only for a network you control.",
    'zone.block': "Block: every connection from outside is refused with a message.",
    'zone.drop': "Drop: every connection from outside is ignored without an answer.",
    'zone.dmz': "DMZ: a computer reachable from outside. Only a few rules are open.",
    'zone.external': "External: for a router that shares its connection.",
    'zone.fedoraworkstation': "FedoraWorkstation: Fedora's desktop default. Every port from 1025 "
                              "to 65535 is open, so programs can listen without a rule.",
    'zone.fedoraserver': "FedoraServer: Fedora's server default. Remote login and the web console.",
    'zone.nm_shared': "Shared connection: used when this PC shares its connection.",
    'zone.rules_for': "Rules for the zone",

    'rules.intro': "Turn a rule on to let that traffic in. Changes wait until you press Apply.",
    'rules.off': "The firewall is off, so these rules can't be changed.",
    'rules.allow': "Allow",
    'rules.open': "Allowed",
    'rules.closed': "Not allowed",
    'rules.covered': "Not allowed by a rule, but this zone already opens its ports.",
    'rules.waiting_on': "Will be allowed when you press Apply.",
    'rules.waiting_off': "Will be closed when you press Apply.",

    'rule.steam_remote_play.title': "Steam Remote Play",
    'rule.steam_remote_play.detail': "Stream games from this PC to another device with Steam.",
    'rule.steam_transfer.title': "Steam game transfers on the home network",
    'rule.steam_transfer.detail': "Copy installed games to or from another PC on your network.",
    'rule.spark_link.title': "Spark Link",
    'rule.spark_link.detail': "Pair this PC with your phone and send files over Wi-Fi.",
    'rule.kde_connect.title': "KDE Connect",
    'rule.kde_connect.detail': "The older phone link. Spark Link replaces it.",
    'rule.find_devices.title': "Be found by name on the network",
    'rule.find_devices.detail': "Lets other devices find this PC by name (mDNS). Spark Link and "
                                "printers use it.",
    'rule.file_sharing.title': "Windows file sharing",
    'rule.file_sharing.detail': "Share folders with other computers (Samba).",
    'rule.remote_login.title': "Remote login (SSH)",
    'rule.remote_login.detail': "Let other computers sign in to this PC from a terminal.",
    'rule.syncthing.title': "Syncthing",
    'rule.syncthing.detail': "Sync folders with other devices.",
    'rule.warpinator.title': "Warpinator",
    'rule.warpinator.detail': "Send files to other PCs on your network.",
    'rule.web_http.title': "Web server (HTTP)",
    'rule.web_http.detail': "Serve web pages from this PC, port 80.",
    'rule.web_https.title': "Web server (HTTPS)",
    'rule.web_https.detail': "Serve secure web pages from this PC, port 443.",

    'ports.intro': "Everything that is open in this zone. A service is a named group of ports; "
                   "a port is one number you opened yourself.",
    'ports.remove': "Remove",
    'ports.keep': "Keep",
    'ports.add': "Open a port",
    'ports.add_button': "Add",
    'ports.format': "A port like 8080 or a range like 5000-5010. Pick TCP or UDP, or write 8080/udp.",
    'ports.bad': "That is not a port. Use a number from 1 to 65535, or a range like 5000-5010.",
    'ports.already': "{port} is already open or waiting to be.",
    'kind.service': "Service",
    'kind.port': "Port",
    'state.open': "Open",
    'state.adding': "Adding",
    'state.removing': "Removing",

    'cli.no_firewalld': "firewalld is not installed",
}

FR = {
    'tab.overview': "Aperçu",
    'tab.rules': "Règles",
    'tab.ports': "Ports",

    'status.watching': "SURVEILLANCE",
    'status.crashed': "QUELQUE CHOSE A ÉCHOUÉ",
    'status.applying': "EN ATTENTE DU MOT DE PASSE",
    'status.starting': "ACTIVATION",
    'status.stopping': "DÉSACTIVATION",
    'status.done': "TERMINÉ",
    'status.failed': "ÉCHEC",
    'status.cancelled': "ANNULÉ",

    'apply.apply': "Appliquer",
    'apply.revert': "Annuler",
    'apply.waiting': "{n} changement(s) pas encore appliqué(s). Appliquer demande votre mot de "
                     "passe une seule fois.",
    'apply.cancelled': "La demande de mot de passe a été annulée.",

    'yes': "Oui",
    'no': "Non",
    'tile.state': "Pare-feu",
    'tile.boot': "Démarre au boot",
    'tile.default': "Zone par défaut",
    'tile.open': "Ouvert dans cette zone",
    'state.on': "ACTIF",
    'state.off': "INACTIF",
    'state.missing': "NON INSTALLÉ",

    'power.off': "Désactiver",
    'power.confirm': "Cliquez encore pour désactiver",
    'power.on': "Activer",
    'power.on_note': "Tant qu'il est actif, les autres ordinateurs n'atteignent que ce que la "
                     "zone autorise.",
    'power.off_note': "Tant qu'il est inactif, tout programme de ce PC qui attend des connexions "
                      "est joignable depuis le réseau.",
    'power.missing': "firewalld n'est pas installé sur ce système, il n'y a rien à contrôler.",

    'hint.stopped': "Le pare-feu est inactif. Rien n'est bloqué, et les règles ne peuvent pas "
                    "être modifiées avant de l'activer.",
    'hint.wide': "La zone {zone} autorise déjà tous les ports de 1025 à 65535 : une règle pour un "
                 "port de cette plage ne change rien ici. Une zone comme public n'ouvre que ce "
                 "qui est listé. Changez la zone de votre réseau dans l'Aperçu.",
    'hint.failed': "Le dernier changement a échoué : {error}",

    'net.heading': "Réseaux connectés",
    'net.none': "Aucune connexion réseau trouvée.",
    'net.zone_for': "Zone pour {name}",
    'net.zone_changing': "{zone} (pas appliqué)",
    'col.network': "Réseau",
    'col.device': "Appareil",
    'col.zone': "Zone",
    'col.kind': "Type",
    'col.what': "Service",
    'col.ports': "Ports",
    'col.state': "État",

    'default.heading': "Zone des nouveaux réseaux",
    'default.note': "Un réseau pour lequel vous n'avez pas choisi de zone utilise celle-ci.",

    'zone.other': "Une zone ajoutée par vous ou par le système.",
    'zone.public': "Public : pour les réseaux inconnus, comme un café. Seules les règles listées "
                   "sont ouvertes.",
    'zone.home': "Maison : un réseau de confiance. La découverte d'appareils et le partage sont "
                 "permis.",
    'zone.work': "Travail : un réseau au travail. Comme Maison, avec moins de raccourcis.",
    'zone.internal': "Interne : votre propre réseau derrière un routeur.",
    'zone.trusted': "Confiance : tout peut entrer. À réserver à un réseau que vous contrôlez.",
    'zone.block': "Bloquer : toute connexion de l'extérieur est refusée avec un message.",
    'zone.drop': "Ignorer : toute connexion de l'extérieur est ignorée sans réponse.",
    'zone.dmz': "DMZ : un ordinateur joignable de l'extérieur. Quelques règles seulement sont "
                "ouvertes.",
    'zone.external': "Externe : pour un routeur qui partage sa connexion.",
    'zone.fedoraworkstation': "FedoraWorkstation : le réglage par défaut de Fedora pour le bureau. "
                              "Tous les ports de 1025 à 65535 sont ouverts, donc un programme "
                              "peut écouter sans règle.",
    'zone.fedoraserver': "FedoraServer : le réglage par défaut de Fedora pour un serveur. Connexion "
                         "à distance et console web.",
    'zone.nm_shared': "Connexion partagée : utilisée quand ce PC partage sa connexion.",
    'zone.rules_for': "Règles de la zone",

    'rules.intro': "Activez une règle pour laisser entrer ce trafic. Les changements attendent "
                   "que vous appuyiez sur Appliquer.",
    'rules.off': "Le pare-feu est inactif, ces règles ne peuvent pas être modifiées.",
    'rules.allow': "Autoriser",
    'rules.open': "Autorisé",
    'rules.closed': "Non autorisé",
    'rules.covered': "Pas autorisé par une règle, mais cette zone ouvre déjà ses ports.",
    'rules.waiting_on': "Sera autorisé quand vous appuierez sur Appliquer.",
    'rules.waiting_off': "Sera fermé quand vous appuierez sur Appliquer.",

    'rule.steam_remote_play.title': "Steam Remote Play",
    'rule.steam_remote_play.detail': "Diffuser des jeux de ce PC vers un autre appareil avec Steam.",
    'rule.steam_transfer.title': "Transferts de jeux Steam sur le réseau local",
    'rule.steam_transfer.detail': "Copier des jeux installés vers un autre PC de votre réseau, ou "
                                  "depuis lui.",
    'rule.spark_link.title': "Spark Link",
    'rule.spark_link.detail': "Jumeler ce PC avec votre téléphone et envoyer des fichiers par Wi-Fi.",
    'rule.kde_connect.title': "KDE Connect",
    'rule.kde_connect.detail': "L'ancien lien avec le téléphone. Spark Link le remplace.",
    'rule.find_devices.title': "Être trouvé par son nom sur le réseau",
    'rule.find_devices.detail': "Permet aux autres appareils de trouver ce PC par son nom (mDNS). "
                                "Spark Link et les imprimantes s'en servent.",
    'rule.file_sharing.title': "Partage de fichiers Windows",
    'rule.file_sharing.detail': "Partager des dossiers avec d'autres ordinateurs (Samba).",
    'rule.remote_login.title': "Connexion à distance (SSH)",
    'rule.remote_login.detail': "Laisser d'autres ordinateurs ouvrir une session sur ce PC depuis "
                                "un terminal.",
    'rule.syncthing.title': "Syncthing",
    'rule.syncthing.detail': "Synchroniser des dossiers avec d'autres appareils.",
    'rule.warpinator.title': "Warpinator",
    'rule.warpinator.detail': "Envoyer des fichiers aux autres PC de votre réseau.",
    'rule.web_http.title': "Serveur web (HTTP)",
    'rule.web_http.detail': "Servir des pages web depuis ce PC, port 80.",
    'rule.web_https.title': "Serveur web (HTTPS)",
    'rule.web_https.detail': "Servir des pages web sécurisées depuis ce PC, port 443.",

    'ports.intro': "Tout ce qui est ouvert dans cette zone. Un service est un groupe de ports "
                   "nommé; un port est un numéro que vous avez ouvert vous-même.",
    'ports.remove': "Retirer",
    'ports.keep': "Garder",
    'ports.add': "Ouvrir un port",
    'ports.add_button': "Ajouter",
    'ports.format': "Un port comme 8080 ou une plage comme 5000-5010. Choisissez TCP ou UDP, ou "
                    "écrivez 8080/udp.",
    'ports.bad': "Ce n'est pas un port. Utilisez un numéro de 1 à 65535, ou une plage comme "
                 "5000-5010.",
    'ports.already': "{port} est déjà ouvert ou en attente de l'être.",
    'kind.service': "Service",
    'kind.port': "Port",
    'state.open': "Ouvert",
    'state.adding': "Ajout",
    'state.removing': "Retrait",

    'cli.no_firewalld': "firewalld n'est pas installé",
}

LANG = ui_language()
TABLE = FR if LANG == 'fr' else EN


def t(key: str, **fields) -> str:
    text = TABLE.get(key) or EN.get(key) or key
    return text.format(**fields) if fields else text
