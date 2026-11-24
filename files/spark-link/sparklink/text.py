"""Every sentence Spark Link shows, in English and in French. The PC's language picks the
table (lang.py); t(id, name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # service: pairing
    'pair.too_many': "Pairing stopped: a phone typed the wrong code five times. Start again "
                     "to get a new code.",
    'pair.timeout': "Pairing stopped: nobody answered on this PC within 2 minutes.",
    'pair.declined': "You didn't pair with {name}.",
    'pair.done': "Paired with {name}.",
    'pair.nothing': "No phone is waiting to pair.",

    # service: events shown in the window
    'ev.connected': "{name} connected.",
    'ev.disconnected': "{name} disconnected.",
    'ev.unpaired': "Unpaired {name}.",
    'ev.unpaired_by_phone': "{name} unpaired itself from this PC.",
    'ev.link': "Opened a link from {name}.",
    'ev.sent': "Sent {file} to {name}.",
    'ev.received': "Saved {file} from {name} in Downloads.",
    'ev.rejected': "{name} didn't take {file}.",
    'ev.failed': "{file}: {why}",

    # service: transfers
    'xfer.lost': "the phone disconnected",
    'xfer.phone_check': "the phone says the file arrived damaged",
    'xfer.cancelled_by': "{name} stopped the transfer",
    'xfer.cancelled': "stopped",
    'xfer.broken': "the phone sent the file out of order",
    'xfer.disk': "couldn't write it: {why}",
    'xfer.check': "it arrived damaged (size or checksum wrong), so it wasn't kept",
    'xfer.no_answer': "the phone didn't answer",
    'send.not_file': "not a file, or over 16 GB",

    # service: notifications
    'offer.title': "{name} wants to send a file",
    'offer.body': "{file} ({size}). Open Spark Link to accept or decline.",
    'received.title': "File from {name}",
    'received.body': "{file} is in Downloads.",
    'notify.app_unknown': "Phone",
    'battery.low_title': "{name}: battery low",
    'battery.low': "{level} % left and not charging.",
    'ring.here_title': "Looking for this PC",
    'ring.here': "{name} is ringing this PC.",

    # service: errors returned to the window and command line
    'err.port': "Can't listen on port {port}: {why}. Another program may be using it.",
    'err.running': "Spark Link is already running in the background.",
    'err.no_device': "That phone isn't paired.",
    'err.no_offer': "That transfer is no longer waiting.",
    'err.not_connected': "No paired phone is connected right now.",
    'err.feature_off': "That's switched off on this PC or on {name}.",
    'err.bad_url': "Only http:// and https:// links can be sent.",
    'err.no_service': "Spark Link isn't running in the background.",

    # window
    'app.status.running': "RUNNING",
    'app.status.listening': "LISTENING ON PORT {port}",
    'app.status.idle': "IDLE: NO PHONE PAIRED",
    'app.status.stopped': "NOT RUNNING",
    'app.tab.devices': "Phones",
    'app.tab.pair': "Pair a phone",
    'app.tab.features': "Features",
    'app.start': "Start Spark Link",
    'app.stopped': "Spark Link runs in the background so your phone can reach this PC. It "
                   "isn't running now.",
    'app.starting': "Starting…",
    'app.start_failed': "Couldn't start the background service: {why}",

    'dev.none': "No phone is paired yet. Open Soot on your phone, go to Link to PC, and "
                "pair it from the Pair a phone tab here.",
    'dev.connected': "CONNECTED",
    'dev.offline': "NOT CONNECTED",
    'dev.last_seen': "last seen {when}",
    'dev.never': "never connected",
    'dev.battery': "battery {level} %",
    'dev.battery_charging': "battery {level} %, charging",
    'dev.key': "key {key}",
    'dev.send_files': "Send files",
    'dev.send_snip': "Send screenshot",
    'dev.snip_none': "No screenshot to send. Take one with Spark Snip (Print) first.",
    'dev.snip_sending': "Offered your last screenshot to {name}. It's sent once the phone "
                        "accepts.",
    'dev.send_link': "Send a link",
    'dev.ring': "Ring",
    'dev.unpair': "Unpair",
    'dev.always_accept': "Accept files without asking",
    'dev.keep': "Keep",
    'dev.transfers': "TRANSFERS",
    'dev.unpair_title': "Unpair {name}?",
    'dev.unpair_confirm': "{name} won't be able to reach this PC until you pair it again.",
    'dev.rung': "Ringing {name}. Tap the phone to stop it.",
    'dev.link_title': "Send a link to {name}",
    'dev.link_prompt': "Paste a web address (http:// or https://)",
    'dev.link_send': "Send",
    'dev.link_sent': "Link sent to {name}.",
    'dev.files_title': "Send files to {name}",
    'dev.files_sending': "Offered {n} file(s) to {name}. They're sent once the phone accepts.",
    'just_now': "just now",
    'minutes_ago': "{n} min ago",
    'hours_ago': "{n} h ago",
    'days_ago': "{n} days ago",

    'pair.intro': "Pairing lets one phone reach this PC. Open Soot on your phone, go to "
                  "Link to PC, and scan this code.",
    'pair.start': "Show a pairing code",
    'pair.stop': "Stop pairing",
    'pair.waiting': "WAITING FOR THE PHONE · CODE EXPIRES IN {left}",
    'pair.expired': "The code expired. Show a new one to pair.",
    'pair.no_camera': "No camera? Copy this link to the phone:",
    'pair.copy': "Copy link",
    'pair.copied': "Link copied.",
    'pair.typed': "Or type in Soot: address {address}, code {code}. Soot will show a key; "
                  "check it reads {key}.",
    'pair.request': "Pair with {name}?",
    'pair.request_key': "The phone's key is {key}.",
    'pair.yes': "Pair",
    'pair.no': "Don't pair",
    'pair.not_listening': "Spark Link can't listen for phones: {why}",
    'pair.no_address': "This PC has no local network address right now.",
    'pair.tailscale': "Away from home, a paired phone with Tailscale on reaches this PC at "
                      "{address}.",

    'feat.url': "Links",
    'feat.url_about': "Open links and tabs sent from your phone in Soot, and send links "
                      "back.",
    'feat.clipboard': "Shared clipboard",
    'feat.clipboard_about': "Text you copy on one device can be pasted on the other. Off "
                            "unless you switch it on: everything you copy goes to the phone.",
    'feat.files': "Files",
    'feat.files_about': "Receive files into Downloads and send files to the phone. You "
                        "confirm each one unless you said otherwise for a phone.",
    'feat.notify': "Phone notifications",
    'feat.notify_about': "Show your phone's notifications on this PC. The phone asks for "
                         "permission to read them.",
    'feat.battery': "Battery",
    'feat.battery_about': "Show the phone's battery here, and warn at 15 %.",
    'feat.ring': "Find my phone",
    'feat.ring_about': "Make the phone ring at full volume from this PC.",
    'feat.local_only': "Everything stays on your local network. Spark Link has no account and "
                       "uses no outside server.",

    'offer.in': "{name} wants to send {file} ({size}).",
    'offer.accept': "Accept",
    'offer.decline': "Decline",
    'xfer.in': "from {name}",
    'xfer.out': "to {name}",
    'xfer.state.waiting': "waiting for you",
    'xfer.state.offered': "waiting for the phone",
    'xfer.state.sending': "sending",
    'xfer.state.sent': "checking",
    'xfer.state.receiving': "receiving",
    'xfer.state.done': "done",
    'xfer.state.failed': "failed",
    'xfer.state.rejected': "declined",
    'xfer.state.cancelled': "stopped",
    'xfer.stop': "Stop",
}

FR = {
    # service: pairing
    'pair.too_many': "Jumelage arrêté : un téléphone a entré le mauvais code cinq fois. "
                     "Recommencez pour obtenir un nouveau code.",
    'pair.timeout': "Jumelage arrêté : personne n'a répondu sur ce PC en 2 minutes.",
    'pair.declined': "Vous n'avez pas jumelé {name}.",
    'pair.done': "Jumelé avec {name}.",
    'pair.nothing': "Aucun téléphone n'attend d'être jumelé.",

    # service: events shown in the window
    'ev.connected': "{name} est connecté.",
    'ev.disconnected': "{name} est déconnecté.",
    'ev.unpaired': "{name} n'est plus jumelé.",
    'ev.unpaired_by_phone': "{name} s'est retiré lui-même de ce PC.",
    'ev.link': "Lien ouvert depuis {name}.",
    'ev.sent': "{file} envoyé à {name}.",
    'ev.received': "{file} reçu de {name} et enregistré dans Téléchargements.",
    'ev.rejected': "{name} n'a pas pris {file}.",
    'ev.failed': "{file} : {why}",

    # service: transfers
    'xfer.lost': "le téléphone s'est déconnecté",
    'xfer.phone_check': "le téléphone dit que le fichier est arrivé endommagé",
    'xfer.cancelled_by': "{name} a arrêté le transfert",
    'xfer.cancelled': "arrêté",
    'xfer.broken': "le téléphone a envoyé le fichier dans le désordre",
    'xfer.disk': "impossible de l'écrire : {why}",
    'xfer.check': "il est arrivé endommagé (taille ou somme de contrôle incorrecte), alors il "
                  "n'a pas été gardé",
    'xfer.no_answer': "le téléphone n'a pas répondu",
    'send.not_file': "ce n'est pas un fichier, ou il dépasse 16 Go",

    # service: notifications
    'offer.title': "{name} veut envoyer un fichier",
    'offer.body': "{file} ({size}). Ouvrez Spark Link pour l'accepter ou le refuser.",
    'received.title': "Fichier de {name}",
    'received.body': "{file} est dans Téléchargements.",
    'notify.app_unknown': "Téléphone",
    'battery.low_title': "{name} : batterie faible",
    'battery.low': "{level} % restant et pas en charge.",
    'ring.here_title': "Recherche de ce PC",
    'ring.here': "{name} fait sonner ce PC.",

    # service: errors returned to the window and command line
    'err.port': "Impossible d'écouter sur le port {port} : {why}. Un autre programme "
                "l'utilise peut-être.",
    'err.running': "Spark Link tourne déjà en arrière-plan.",
    'err.no_device': "Ce téléphone n'est pas jumelé.",
    'err.no_offer': "Ce transfert n'est plus en attente.",
    'err.not_connected': "Aucun téléphone jumelé n'est connecté en ce moment.",
    'err.feature_off': "C'est désactivé sur ce PC ou sur {name}.",
    'err.bad_url': "Seuls les liens http:// et https:// peuvent être envoyés.",
    'err.no_service': "Spark Link ne tourne pas en arrière-plan.",

    # window
    'app.status.running': "EN MARCHE",
    'app.status.listening': "À L'ÉCOUTE SUR LE PORT {port}",
    'app.status.idle': "INACTIF : AUCUN TÉLÉPHONE JUMELÉ",
    'app.status.stopped': "ARRÊTÉ",
    'app.tab.devices': "Téléphones",
    'app.tab.pair': "Jumeler un téléphone",
    'app.tab.features': "Fonctions",
    'app.start': "Démarrer Spark Link",
    'app.stopped': "Spark Link tourne en arrière-plan pour que votre téléphone puisse joindre "
                   "ce PC. Il n'est pas en marche en ce moment.",
    'app.starting': "Démarrage…",
    'app.start_failed': "Impossible de démarrer le service d'arrière-plan : {why}",

    'dev.none': "Aucun téléphone n'est jumelé pour l'instant. Ouvrez Soot sur votre téléphone, "
                "allez dans Link to PC, et jumelez-le à partir de l'onglet Jumeler un "
                "téléphone ici.",
    'dev.connected': "CONNECTÉ",
    'dev.offline': "NON CONNECTÉ",
    'dev.last_seen': "vu {when}",
    'dev.never': "jamais connecté",
    'dev.battery': "batterie {level} %",
    'dev.battery_charging': "batterie {level} %, en charge",
    'dev.key': "clé {key}",
    'dev.send_files': "Envoyer des fichiers",
    'dev.send_snip': "Envoyer la capture",
    'dev.snip_none': "Aucune capture à envoyer. Prenez-en une avec Spark Snip (Impr. écran) "
                     "d'abord.",
    'dev.snip_sending': "Dernière capture proposée à {name}. Elle part quand le téléphone "
                        "accepte.",
    'dev.send_link': "Envoyer un lien",
    'dev.ring': "Faire sonner",
    'dev.unpair': "Oublier",
    'dev.always_accept': "Accepter les fichiers sans demander",
    'dev.keep': "Garder",
    'dev.transfers': "TRANSFERTS",
    'dev.unpair_title': "Oublier {name}?",
    'dev.unpair_confirm': "{name} ne pourra plus joindre ce PC tant que vous ne le jumelez pas "
                          "de nouveau.",
    'dev.rung': "{name} sonne. Touchez le téléphone pour l'arrêter.",
    'dev.link_title': "Envoyer un lien à {name}",
    'dev.link_prompt': "Collez une adresse Web (http:// ou https://)",
    'dev.link_send': "Envoyer",
    'dev.link_sent': "Lien envoyé à {name}.",
    'dev.files_title': "Envoyer des fichiers à {name}",
    'dev.files_sending': "{n} fichier(s) proposé(s) à {name}. Ils partent quand le téléphone "
                         "accepte.",
    'just_now': "à l'instant",
    'minutes_ago': "il y a {n} min",
    'hours_ago': "il y a {n} h",
    'days_ago': "il y a {n} jours",

    'pair.intro': "Le jumelage permet à un téléphone de joindre ce PC. Ouvrez Soot sur votre "
                  "téléphone, allez dans Link to PC, et balayez ce code.",
    'pair.start': "Afficher un code de jumelage",
    'pair.stop': "Arrêter le jumelage",
    'pair.waiting': "EN ATTENTE DU TÉLÉPHONE · LE CODE EXPIRE DANS {left}",
    'pair.expired': "Le code a expiré. Affichez-en un nouveau pour jumeler.",
    'pair.no_camera': "Pas de caméra? Copiez ce lien sur le téléphone :",
    'pair.copy': "Copier le lien",
    'pair.copied': "Lien copié.",
    'pair.typed': "Ou entrez dans Soot : adresse {address}, code {code}. Soot affichera une "
                  "clé; vérifiez qu'elle indique {key}.",
    'pair.request': "Jumeler avec {name}?",
    'pair.request_key': "La clé du téléphone est {key}.",
    'pair.yes': "Jumeler",
    'pair.no': "Ne pas jumeler",
    'pair.not_listening': "Spark Link ne peut pas écouter les téléphones : {why}",
    'pair.no_address': "Ce PC n'a pas d'adresse sur le réseau local en ce moment.",
    'pair.tailscale': "Hors de la maison, un téléphone jumelé avec Tailscale activé joint ce PC à "
                      "{address}.",

    'feat.url': "Liens",
    'feat.url_about': "Ouvrir dans Soot les liens et les onglets envoyés de votre téléphone, "
                      "et lui renvoyer des liens.",
    'feat.clipboard': "Presse-papiers partagé",
    'feat.clipboard_about': "Le texte copié sur un appareil peut être collé sur l'autre. "
                            "Désactivé tant que vous ne l'activez pas : tout ce que vous "
                            "copiez va au téléphone.",
    'feat.files': "Fichiers",
    'feat.files_about': "Recevoir des fichiers dans Téléchargements et envoyer des fichiers au "
                        "téléphone. Vous confirmez chacun, sauf si vous avez dit autrement pour "
                        "un téléphone.",
    'feat.notify': "Notifications du téléphone",
    'feat.notify_about': "Afficher les notifications de votre téléphone sur ce PC. Le téléphone "
                         "demande la permission de les lire.",
    'feat.battery': "Batterie",
    'feat.battery_about': "Afficher la batterie du téléphone ici, et avertir à 15 %.",
    'feat.ring': "Retrouver mon téléphone",
    'feat.ring_about': "Faire sonner le téléphone à plein volume à partir de ce PC.",
    'feat.local_only': "Tout reste sur votre réseau local. Spark Link n'a pas de compte et "
                       "n'utilise aucun serveur extérieur.",

    'offer.in': "{name} veut envoyer {file} ({size}).",
    'offer.accept': "Accepter",
    'offer.decline': "Refuser",
    'xfer.in': "de {name}",
    'xfer.out': "à {name}",
    'xfer.state.waiting': "attend votre réponse",
    'xfer.state.offered': "attend le téléphone",
    'xfer.state.sending': "envoi",
    'xfer.state.sent': "vérification",
    'xfer.state.receiving': "réception",
    'xfer.state.done': "terminé",
    'xfer.state.failed': "échec",
    'xfer.state.rejected': "refusé",
    'xfer.state.cancelled': "arrêté",
    'xfer.stop': "Arrêter",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(_id: str, **kw) -> str:
    text = _T.get(_id) or EN.get(_id) or _id
    return text.format(**kw) if kw else text
