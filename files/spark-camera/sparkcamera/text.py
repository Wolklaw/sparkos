"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # header and status
    'tab.camera': "CAMERA",
    'tab.voice': "VOICE",
    'status.ready': "READY",
    'status.live': "LIVE  ·  {cam}",
    'status.recording': "RECORDING",
    'status.paused': "PAUSED",
    'status.saving': "SAVING",
    'status.saved': "SAVED  ·  {name}",
    'status.trashed': "MOVED TO THE TRASH  ·  {name}",
    'status.error': "SOMETHING WENT WRONG",
    'status.finish_first': "STOP THE RECORDING FIRST",

    # camera: the picture
    'cam.none': "No camera found",
    'cam.none_hint': "Plug one in, then press the refresh button on the right.",
    'cam.starting': "Starting the camera",
    'cam.failed': "The camera didn't start",
    'cam.stopped': "The camera stopped",
    'cam.no_picture': "No picture yet",
    'cam.no_picture_hint': "The camera is open but sends nothing. Another program may be using "
                           "it; close it and press refresh.",
    'cam.no_gstreamer': "GStreamer is missing",
    'cam.no_gstreamer_hint': "Spark Camera needs GStreamer and its Python bindings "
                             "(python3-gobject).",

    # camera: controls
    'mode.photo': "PHOTO",
    'mode.video': "VIDEO",
    'shutter.photo': "Take photo",
    'shutter.record': "Record",
    'shutter.stop': "Stop recording",
    'shutter.cancel': "Cancel",
    'side.camera': "Camera",
    'side.size': "Size",
    'side.mic': "Microphone",
    'side.format': "Format",
    'side.options': "Options",
    'side.countdown': "Countdown, seconds",
    'side.saved_to': "Saved to",
    'where.photos': "Photos",
    'where.videos': "Videos",
    'toggle.sound': "Sound",
    'toggle.mirror': "Mirror",
    'countdown.off': "OFF",
    'hint.no_encoder': "No video encoder is installed.",
    'hint.with_sound': "With sound from the microphone.",
    'gallery.title': "Latest",
    'gallery.empty': "Nothing yet. Photos and videos you take show up here; click one to "
                     "open it.",
    'gallery.photos_folder': "Photos folder",
    'gallery.videos_folder': "Videos folder",
    'file.photo': "Photo",
    'file.video': "Video",
    'file.recording': "Recording",

    # voice
    'voice.heading': "VOICE RECORDER",
    'voice.record': "Record",
    'voice.pause': "Pause",
    'voice.resume': "Resume",
    'voice.stop': "Stop",
    'voice.ready': "Ready. The bars move with the microphone; nothing is saved until you "
                   "press Record.",
    'voice.recording': "Recording.",
    'voice.paused': "Paused. Resume adds to the same file.",
    'voice.no_mic': "No microphone found. Plug one in and press refresh.",
    'voice.no_encoder': "No audio encoder is installed.",
    'voice.mic_failed': "The microphone didn't open: {error}",
    'voice.stopped': "The recording stopped: {error}. What was recorded is saved.",
    'voice.recordings': "Recordings",
    'voice.open_folder': "Open the folder",
    'voice.empty': "No recordings yet.",
    'col.name': "Name",
    'col.length': "Length",
    'col.size': "Size",
    'col.date': "Date",
    'rename.title': "Rename the recording",
    'rename.message': "The new name, without the file type.",
    'delete.title': "Move to the trash?",
    'delete.message': "{name} goes to the trash. You can restore it from there.",

    # errors
    'error.open_title': "Couldn't open it",
    'error.open': "Nothing could open {path}.",
    'error.photo_title': "Couldn't take the photo",
    'error.no_frame': "The camera hasn't sent a picture yet. Try again in a second.",
    'error.photo_save': "Couldn't save {path}: {error}",
    'error.video_title': "Couldn't record the video",
    'error.video_start': "The recording didn't start: {error}",
    'error.video_empty': "The recording is empty, so it was removed. The camera may have "
                         "stopped sending pictures.",
    'error.voice_title': "Couldn't record your voice",
    'error.voice_start': "The recording didn't start: {error}",
    'error.voice_empty': "The recording is empty, so it was removed. Check the microphone.",
    'error.play_title': "Couldn't play it",
    'error.play': "Playback didn't start: {error}",
    'error.rename_title': "Couldn't rename it",
    'error.rename_empty': "The name is empty.",
    'error.rename_exists': "{name} already exists.",
    'error.rename': "Renaming failed: {error}",
    'error.delete_title': "Couldn't move it to the trash",
    'error.delete': "{name} stays where it is: {error}",
}

FR = {
    # en-tête et état
    'tab.camera': "CAMÉRA",
    'tab.voice': "VOIX",
    'status.ready': "PRÊT",
    'status.live': "EN DIRECT  ·  {cam}",
    'status.recording': "ENREGISTREMENT",
    'status.paused': "EN PAUSE",
    'status.saving': "ENREGISTRE",
    'status.saved': "ENREGISTRÉ  ·  {name}",
    'status.trashed': "MIS À LA CORBEILLE  ·  {name}",
    'status.error': "QUELQUE CHOSE A ÉCHOUÉ",
    'status.finish_first': "ARRÊTEZ D'ABORD L'ENREGISTREMENT",

    # caméra : l'image
    'cam.none': "Aucune caméra trouvée",
    'cam.none_hint': "Branchez-en une, puis appuyez sur le bouton d'actualisation à droite.",
    'cam.starting': "Démarrage de la caméra",
    'cam.failed': "La caméra n'a pas démarré",
    'cam.stopped': "La caméra s'est arrêtée",
    'cam.no_picture': "Pas encore d'image",
    'cam.no_picture_hint': "La caméra est ouverte mais n'envoie rien. Un autre programme "
                           "l'utilise peut-être ; fermez-le et actualisez.",
    'cam.no_gstreamer': "GStreamer est absent",
    'cam.no_gstreamer_hint': "Spark Camera a besoin de GStreamer et de ses liens Python "
                             "(python3-gobject).",

    # caméra : les réglages
    'mode.photo': "PHOTO",
    'mode.video': "VIDÉO",
    'shutter.photo': "Prendre une photo",
    'shutter.record': "Enregistrer",
    'shutter.stop': "Arrêter",
    'shutter.cancel': "Annuler",
    'side.camera': "Caméra",
    'side.size': "Taille",
    'side.mic': "Microphone",
    'side.format': "Format",
    'side.options': "Options",
    'side.countdown': "Compte à rebours, secondes",
    'side.saved_to': "Enregistré dans",
    'where.photos': "Photos",
    'where.videos': "Vidéos",
    'toggle.sound': "Son",
    'toggle.mirror': "Miroir",
    'countdown.off': "NON",
    'hint.no_encoder': "Aucun encodeur vidéo n'est installé.",
    'hint.with_sound': "Avec le son du microphone.",
    'gallery.title': "Récents",
    'gallery.empty': "Rien pour l'instant. Les photos et vidéos prises apparaissent ici ; "
                     "cliquez-en une pour l'ouvrir.",
    'gallery.photos_folder': "Dossier photos",
    'gallery.videos_folder': "Dossier vidéos",
    'file.photo': "Photo",
    'file.video': "Vidéo",
    'file.recording': "Enregistrement",

    # voix
    'voice.heading': "ENREGISTREUR DE VOIX",
    'voice.record': "Enregistrer",
    'voice.pause': "Pause",
    'voice.resume': "Reprendre",
    'voice.stop': "Arrêter",
    'voice.ready': "Prêt. Les barres suivent le microphone ; rien n'est gardé avant "
                   "d'appuyer sur Enregistrer.",
    'voice.recording': "Enregistrement en cours.",
    'voice.paused': "En pause. Reprendre continue dans le même fichier.",
    'voice.no_mic': "Aucun microphone trouvé. Branchez-en un et actualisez.",
    'voice.no_encoder': "Aucun encodeur audio n'est installé.",
    'voice.mic_failed': "Le microphone ne s'est pas ouvert : {error}",
    'voice.stopped': "L'enregistrement s'est arrêté : {error}. Ce qui a été enregistré est "
                     "gardé.",
    'voice.recordings': "Enregistrements",
    'voice.open_folder': "Ouvrir le dossier",
    'voice.empty': "Aucun enregistrement pour l'instant.",
    'col.name': "Nom",
    'col.length': "Durée",
    'col.size': "Taille",
    'col.date': "Date",
    'rename.title': "Renommer l'enregistrement",
    'rename.message': "Le nouveau nom, sans le type de fichier.",
    'delete.title': "Mettre à la corbeille ?",
    'delete.message': "{name} va à la corbeille. Vous pourrez le restaurer de là.",

    # erreurs
    'error.open_title': "Impossible de l'ouvrir",
    'error.open': "Rien n'a pu ouvrir {path}.",
    'error.photo_title': "Impossible de prendre la photo",
    'error.no_frame': "La caméra n'a pas encore envoyé d'image. Réessayez dans une seconde.",
    'error.photo_save': "Impossible d'enregistrer {path} : {error}",
    'error.video_title': "Impossible d'enregistrer la vidéo",
    'error.video_start': "L'enregistrement n'a pas démarré : {error}",
    'error.video_empty': "L'enregistrement est vide, il a donc été retiré. La caméra a "
                         "peut-être cessé d'envoyer des images.",
    'error.voice_title': "Impossible d'enregistrer votre voix",
    'error.voice_start': "L'enregistrement n'a pas démarré : {error}",
    'error.voice_empty': "L'enregistrement est vide, il a donc été retiré. Vérifiez le "
                         "microphone.",
    'error.play_title': "Impossible de le lire",
    'error.play': "La lecture n'a pas démarré : {error}",
    'error.rename_title': "Impossible de le renommer",
    'error.rename_empty': "Le nom est vide.",
    'error.rename_exists': "{name} existe déjà.",
    'error.rename': "Le renommage a échoué : {error}",
    'error.delete_title': "Impossible de le mettre à la corbeille",
    'error.delete': "{name} reste où il est : {error}",
}

_TABLE = FR if ui_language() == 'fr' else EN


def t(key: str, **kw) -> str:
    text = _TABLE.get(key)
    if text is None:
        text = EN.get(key, key)
    return text.format(**kw) if kw else text
