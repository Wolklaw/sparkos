"""Every sentence Spark Clips shows or prints, in English and in French. The PC's language
picks the table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # header status
    'status.recording': "RECORDING A REPLAY",
    'status.waiting': "WAITING FOR A GAME",
    'status.off': "REPLAY OFF",
    'status.starting': "STARTING",
    'status.needs_setup': "PICK THE SCREEN",
    'status.error': "SOMETHING WENT WRONG",
    'status.service_off': "SERVICE NOT RUNNING",
    'status.saving': "SAVING THE CLIP",
    'status.saved': "SAVED  ·  {name}",
    'status.trashed': "MOVED TO THE TRASH  ·  {name}",
    'status.trimming': "CUTTING",
    'status.copied': "COPIED  ·  {name}",

    # the live panel
    'state.off': "Replay off",
    'state.waiting': "Waiting for a game",
    'state.starting': "Starting",
    'state.recording': "Recording a replay",
    'state.needs_setup': "Pick the screen first",
    'state.error': "Not recording",
    'state.service_off': "Service not running",
    'detail.service_off': "The service keeps the replay going when this window is closed. "
                          "Start it to record.",
    'detail.game': "Game: {name}",
    'detail.held': "Holding {held} of {keep}",
    'detail.tracks': "{n} audio track(s)",
    'detail.waiting': "The replay starts when a game does.",
    'detail.waiting_any': "The replay starts in a moment.",
    'button.save': "Save a clip",
    'button.setup': "Set up the screen",
    'button.service': "Start the service",
    'button.cancel': "Cancel",
    'toggle.keep': "Keep a replay",
    'shortcut.line': "Save a clip from anywhere with {keys}.",
    'shortcut.taken': "{keys} is taken by {name}, so it will not save a clip. Change it in "
                      "System Settings, Shortcuts.",

    # problems the service reports
    'problem.missing': "GStreamer is missing parts: {detail}. Install them and restart the "
                       "service.",
    'problem.no_hevc': "No HEVC encoder is installed. Pick H.264.",
    'problem.no_encoder': "No video encoder is installed.",
    'problem.ram': "A buffer this long needs about {detail} MB of memory, more than a quarter "
                   "of what is free. Pick a shorter replay or a lower bitrate.",
    'problem.portal': "The screen could not be shared: {detail}",
    'problem.pipeline': "The recording stopped and would not restart: {detail}",
    'problem.not_recording': "Nothing is being recorded, so there is nothing to save.",
    'problem.too_early': "The replay has barely started. Try again in a few seconds.",
    'problem.save_failed': "The clip was not saved: {detail}",

    # the screen share
    'rec.no_gi': "Python's GObject bindings are missing (python3-gobject).",
    'rec.no_bus': "Can't reach the desktop's session bus: {error}",
    'rec.no_answer': "The desktop did not answer the screen share request.",
    'rec.portal': "The desktop portal failed: {error}",
    'rec.declined': "The screen share was declined.",
    'rec.refused': "The desktop refused the screen share.",
    'rec.no_screen': "The desktop shared no screen.",

    # notification
    'notify.saved': "Clip saved ({seconds} s)",
    'notify.open': "Open",
    'notify.folder': "Show in folder",

    # the clip list
    'clips.title': "Clips",
    'clips.empty': "No clips yet. Press the shortcut or Save a clip while a game is running, "
                   "and the clip shows up here.",
    'tool.play': "Play",
    'tool.trim': "Trim",
    'tool.rename': "Rename",
    'tool.delete': "Delete",
    'tool.copy': "Copy",
    'tool.folder': "Folder",

    # settings
    'side.length': "Replay length",
    'side.record': "Record",
    'side.codec': "Video",
    'side.fps': "Frame rate",
    'side.bitrate': "Quality",
    'side.size': "Picture size",
    'length.seconds': "{n} S",
    'length.minutes': "{n} MIN",
    'toggle.only_game': "Only while a game runs",
    'toggle.sound': "Game sound",
    'toggle.mic': "Microphone",
    'codec.h264': "H.264",
    'codec.hevc': "HEVC",
    'fps.native': "SCREEN",
    'bitrate.value': "Up to {n} Mbit/s",
    'size.native': "Screen size",
    'size.1080': "1080p",
    'size.720': "720p",
    'memory.estimate': "The replay holds about {size} in memory.",
    'memory.free': "{size} is free.",
    'memory.too_big': "That is more than a quarter of it. The replay will not start.",
    'encoder.line': "Encoder: {name}",
    'encoder.none': "Encoder: none found",
    'encoder.none_short': "none",

    # trim
    'trim.title': "Trim the clip",
    'trim.start': "Start",
    'trim.end': "End",
    'trim.summary': "{start} to {end}, {length} long",
    'trim.note': "The cut is lossless: the picture is not re-encoded, so the start moves back "
                 "to the nearest keyframe, up to about a second. The original stays.",
    'trim.save': "Save the trimmed clip",

    # dialogs
    'rename.title': "Rename the clip",
    'rename.message': "The new name, without the file type.",
    'delete.title': "Move to the trash?",
    'delete.message': "{name} goes to the trash. You can restore it from there.",

    # errors
    'error.open_title': "Can't open it",
    'error.open': "Nothing could open {path}.",
    'error.save_title': "The clip was not saved",
    'error.no_service': "The service is not running. Start it from this window.",
    'error.service_title': "The service did not start",
    'error.service': "It said: {error}",
    'error.copy_title': "Can't copy it",
    'error.copy': "The clipboard refused the file: {error}",
    'error.rename_title': "Can't rename it",
    'error.exists': "{name} already exists.",
    'error.rename': "Renaming {name} failed: {error}",
    'error.delete_title': "Can't move it to the trash",
    'error.delete': "{name} stays where it is: {error}",
    'error.trim_title': "Can't trim it",
    'error.trim_unreadable': "{name} is too short or can't be read.",
    'error.trim': "The cut failed: {error}",

    # the command line
    'cli.service_off': "The Spark Clips service is not running. Start it from the window or "
                       "with: systemctl --user enable --now spark-clips",
    'cli.state': "State: {state}",
    'cli.game': "Game: {name} (found by {source})",
    'cli.held': "Holding {held} of {keep}, {size} in memory",
    'cli.problem': "Problem: {text}",
    'cli.encoder': "Encoder: {name}, audio: {audio}",
}

FR = {
    'status.recording': "REPLAY EN COURS",
    'status.waiting': "EN ATTENTE D'UN JEU",
    'status.off': "REPLAY ÉTEINT",
    'status.starting': "DÉMARRAGE",
    'status.needs_setup': "CHOISIR L'ÉCRAN",
    'status.error': "QUELQUE CHOSE A ÉCHOUÉ",
    'status.service_off': "SERVICE ARRÊTÉ",
    'status.saving': "ENREGISTREMENT DU CLIP",
    'status.saved': "ENREGISTRÉ  ·  {name}",
    'status.trashed': "À LA CORBEILLE  ·  {name}",
    'status.trimming': "DÉCOUPE",
    'status.copied': "COPIÉ  ·  {name}",

    'state.off': "Replay éteint",
    'state.waiting': "En attente d'un jeu",
    'state.starting': "Démarrage",
    'state.recording': "Replay en cours",
    'state.needs_setup': "Choisissez d'abord l'écran",
    'state.error': "Pas d'enregistrement",
    'state.service_off': "Service arrêté",
    'detail.service_off': "Le service garde le replay en marche quand cette fenêtre est "
                          "fermée. Démarrez-le pour enregistrer.",
    'detail.game': "Jeu : {name}",
    'detail.held': "{held} gardées sur {keep}",
    'detail.tracks': "{n} piste(s) audio",
    'detail.waiting': "Le replay démarre avec un jeu.",
    'detail.waiting_any': "Le replay démarre dans un instant.",
    'button.save': "Garder un clip",
    'button.setup': "Choisir l'écran",
    'button.service': "Démarrer le service",
    'button.cancel': "Annuler",
    'toggle.keep': "Garder un replay",
    'shortcut.line': "Gardez un clip de n'importe où avec {keys}.",
    'shortcut.taken': "{keys} est pris par {name} : il ne gardera pas de clip. Changez-le "
                      "dans Configuration du système, Raccourcis.",

    'problem.missing': "Il manque des éléments à GStreamer : {detail}. Installez-les et "
                       "redémarrez le service.",
    'problem.no_hevc': "Aucun encodeur HEVC n'est installé. Choisissez H.264.",
    'problem.no_encoder': "Aucun encodeur vidéo n'est installé.",
    'problem.ram': "Un tampon de cette durée demande environ {detail} Mo de mémoire, plus du "
                   "quart de ce qui est libre. Choisissez un replay plus court ou une qualité "
                   "plus basse.",
    'problem.portal': "L'écran n'a pas pu être partagé : {detail}",
    'problem.pipeline': "L'enregistrement s'est arrêté et ne redémarre pas : {detail}",
    'problem.not_recording': "Rien n'est enregistré, il n'y a donc rien à garder.",
    'problem.too_early': "Le replay vient de démarrer. Réessayez dans quelques secondes.",
    'problem.save_failed': "Le clip n'a pas été enregistré : {detail}",

    'rec.no_gi': "Les liaisons Python de GObject manquent (python3-gobject).",
    'rec.no_bus': "Impossible de joindre le bus de session du bureau : {error}",
    'rec.no_answer': "Le bureau n'a pas répondu à la demande de partage d'écran.",
    'rec.portal': "Le portail du bureau a échoué : {error}",
    'rec.declined': "Le partage d'écran a été refusé.",
    'rec.refused': "Le bureau a refusé le partage d'écran.",
    'rec.no_screen': "Le bureau n'a partagé aucun écran.",

    'notify.saved': "Clip enregistré ({seconds} s)",
    'notify.open': "Ouvrir",
    'notify.folder': "Afficher dans le dossier",

    'clips.title': "Clips",
    'clips.empty': "Pas encore de clip. Appuyez sur le raccourci ou sur Garder un clip "
                   "pendant un jeu, et le clip apparaît ici.",
    'tool.play': "Lire",
    'tool.trim': "Couper",
    'tool.rename': "Renommer",
    'tool.delete': "Supprimer",
    'tool.copy': "Copier",
    'tool.folder': "Dossier",

    'side.length': "Durée du replay",
    'side.record': "Enregistrer",
    'side.codec': "Vidéo",
    'side.fps': "Images par seconde",
    'side.bitrate': "Qualité",
    'side.size': "Taille de l'image",
    'length.seconds': "{n} S",
    'length.minutes': "{n} MIN",
    'toggle.only_game': "Seulement pendant un jeu",
    'toggle.sound': "Son du jeu",
    'toggle.mic': "Microphone",
    'codec.h264': "H.264",
    'codec.hevc': "HEVC",
    'fps.native': "ÉCRAN",
    'bitrate.value': "Jusqu'à {n} Mbit/s",
    'size.native': "Taille de l'écran",
    'size.1080': "1080p",
    'size.720': "720p",
    'memory.estimate': "Le replay occupe environ {size} de mémoire.",
    'memory.free': "{size} sont libres.",
    'memory.too_big': "C'est plus du quart. Le replay ne démarrera pas.",
    'encoder.line': "Encodeur : {name}",
    'encoder.none': "Encodeur : aucun trouvé",
    'encoder.none_short': "aucun",

    'trim.title': "Couper le clip",
    'trim.start': "Début",
    'trim.end': "Fin",
    'trim.summary': "{start} à {end}, {length} de long",
    'trim.note': "La coupe est sans perte : l'image n'est pas ré-encodée, le début recule donc "
                 "jusqu'à l'image clé la plus proche, d'environ une seconde au plus. "
                 "L'original reste.",
    'trim.save': "Enregistrer la coupe",

    'rename.title': "Renommer le clip",
    'rename.message': "Le nouveau nom, sans le type de fichier.",
    'delete.title': "Mettre à la corbeille ?",
    'delete.message': "{name} va à la corbeille. Vous pourrez le restaurer de là.",

    'error.open_title': "Impossible de l'ouvrir",
    'error.open': "Rien n'a pu ouvrir {path}.",
    'error.save_title': "Le clip n'a pas été enregistré",
    'error.no_service': "Le service est arrêté. Démarrez-le depuis cette fenêtre.",
    'error.service_title': "Le service n'a pas démarré",
    'error.service': "Il a répondu : {error}",
    'error.copy_title': "Impossible de le copier",
    'error.copy': "Le presse-papiers a refusé le fichier : {error}",
    'error.rename_title': "Impossible de le renommer",
    'error.exists': "{name} existe déjà.",
    'error.rename': "Le renommage de {name} a échoué : {error}",
    'error.delete_title': "Impossible de le mettre à la corbeille",
    'error.delete': "{name} reste où il est : {error}",
    'error.trim_title': "Impossible de le couper",
    'error.trim_unreadable': "{name} est trop court ou illisible.",
    'error.trim': "La coupe a échoué : {error}",

    'cli.service_off': "Le service Spark Clips est arrêté. Démarrez-le depuis la fenêtre ou "
                       "avec : systemctl --user enable --now spark-clips",
    'cli.state': "État : {state}",
    'cli.game': "Jeu : {name} (trouvé par {source})",
    'cli.held': "{held} gardées sur {keep}, {size} en mémoire",
    'cli.problem': "Problème : {text}",
    'cli.encoder': "Encodeur : {name}, audio : {audio}",
}

_TABLE = FR if ui_language() == 'fr' else EN


def t(key: str, **kw) -> str:
    text = _TABLE.get(key)
    if text is None:
        text = EN.get(key, key)
    return text.format(**kw) if kw else text
