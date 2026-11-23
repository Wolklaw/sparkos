"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    'tab.overview': "Overview",
    'tab.fans': "Fans",
    'tab.rgb': "Spark RGB",
    'tab.drivers': "Drivers & firmware",

    'status.watching': "WATCHING",
    'status.crashed': "SOMETHING WENT WRONG",
    'status.saving': "WAITING FOR PASSWORD",
    'status.saved': "DONE",
    'status.failed': "FAILED",
    'status.scanning': "LOOKING FOR LIGHTS",
    'status.applying': "APPLYING",
    'status.checking': "CHECKING LVFS",
    'status.updating': "UPDATING FIRMWARE",

    'col.fan': "Fan",
    'col.speed': "Speed",
    'col.duty': "Power",
    'col.control': "Controlled by",
    'col.device': "Device",
    'col.version': "Version",
    'col.state': "State",

    'tile.cpu': "CPU",
    'tile.gpu': "GPU",
    'tile.liquid': "Liquid",
    'tile.profile': "Fans",
    'tile.no_liquid': "no sensor",
    'profile.spark': "Spark, {n}",
    'profile.firmware': "Firmware",
    'overview.fans': "Fans and pumps",
    'overview.none': "No fan was found. The fans on the motherboard show up once its sensor "
                     "driver is loaded.",
    'mode.spark': "Spark Controller",
    'mode.firmware': "Firmware (automatic)",
    'mode.readonly': "Firmware (read only)",
    'mode.error': "Spark, but it failed",
    'hint.board_driver': "The motherboard's fan headers are not visible yet. Spark loads the "
                         "driver for them (nct6775) at boot: restart the PC once.",
    'hint.service_off': "Fan curves are saved, but the fan service is not running. The fans are "
                        "on their own control.",

    'fans.list': "Fans",
    'fans.use_spark': "Spark controls this fan",
    'fans.source': "Temperature",
    'fans.fixed': "Fixed power",
    'fans.minimum': "Never below",
    'fans.curve_help': "Drag a point to move it. Click empty space to add one. Double-click a "
                       "point to remove it. Editing a preset turns it into your own curve. "
                       "The gold line is the temperature now.",
    'fans.apply': "Apply",
    'fans.revert': "Revert",
    'fans.hand_back': "Hand all fans back",
    'fans.unsaved': "Changes not applied yet. Apply asks for your password once.",
    'fans.applied': "Applied. Spark controls {n} fan(s) and gives them back when it stops.",
    'fans.applied_none': "Applied. Every fan is back on its own control.",
    'fans.handed_back': "Every fan is back on its own control.",
    'fans.failed': "Not applied: {error}",
    'fans.cancelled': "The password prompt was cancelled.",
    'fans.none': "No fan found.",
    'fans.read_only': "This fan can be read but not set: its chip has no power control Spark "
                      "can use.",
    'fans.live': "{rpm}  ·  {duty}  ·  {mode}  ·  {temp}",

    'preset.quiet': "Quiet",
    'preset.balanced': "Balanced",
    'preset.performance': "Performance",
    'preset.fixed': "Fixed",
    'source.cpu': "CPU",
    'source.gpu': "GPU",
    'source.liquid': "Liquid",
    'source.max': "Hotter",

    'rgb.devices': "Lights",
    'rgb.rescan': "Look again",
    'rgb.scanning': "Looking for lights...",
    'rgb.none': "No controllable lights found.",
    'rgb.effect': "Effect",
    'rgb.colour': "Colour",
    'rgb.pick': "Other...",
    'rgb.speed': "Speed",
    'rgb.apply': "Apply",
    'rgb.apply_all': "Apply to all",
    'rgb.off': "Lights off",
    'rgb.applied': "Applied to {n} device(s) and saved. It is applied again at login.",
    'rgb.is_off': "Lights off, and they stay off at login.",
    'rgb.failed': "Failed: {errors}",
    'rgb.note': "NZXT and similar USB controllers go through liquidctl. The motherboard, mice, "
                "keyboards and memory go through OpenRGB. Effects that a device doesn't have "
                "fall back to its closest one.",
    'effect.static': "Static",
    'effect.breathing': "Breathing",
    'effect.fade': "Fade",
    'effect.spectrum': "Spectrum",
    'effect.off': "Off",
    'speed.slow': "Slow",
    'speed.normal': "Normal",
    'speed.fast': "Fast",

    'drivers.firmware': "Device firmware",
    'drivers.firmware_note': "From LVFS, through fwupd. Installing asks for your password, and "
                             "some updates finish at the next restart.",
    'drivers.check': "Check for updates",
    'drivers.install': "Install updates",
    'drivers.no_fwupd': "fwupd is not installed.",
    'drivers.reading': "Reading devices...",
    'drivers.checking': "Asking LVFS...",
    'drivers.installing': "Installing. Don't turn the PC off.",
    'drivers.installed': "Done. {detail}",
    'drivers.failed': "Failed: {error}",
    'drivers.n_updates': "{n} update(s) available.",
    'drivers.none_pending': "Nothing to update.",
    'drivers.update_to': "Update to {version}",
    'drivers.up_to_date': "Up to date",
    'drivers.not_updatable': "Not updatable here",
    'drivers.release': "Version {version}",
    'drivers.reboot': "Needs a restart to finish.",
    'drivers.system': "System drivers",
    'drivers.system_note': "Updated with the system image, through Spark Update.",
    'drivers.kernel': "Kernel",
    'drivers.mesa': "Mesa (graphics)",
    'drivers.gpu_firmware': "GPU firmware (amdgpu)",
    'drivers.unknown': "unknown",
    'drivers.bios': "BIOS",
    'drivers.board': "Board",
    'drivers.bios_version': "BIOS version",
    'drivers.bios_date': "BIOS date",
    'drivers.bios_vendor': "BIOS vendor",
    'drivers.bios_note': "Spark shows the BIOS version but doesn't flash it. If LVFS lists "
                         "your board above, update it there. Otherwise use the board "
                         "maker's tool.",

    'cli.rgb_applied': "RGB: applied to {n} device(s)",
    'cli.rgb_none': "RGB: nothing saved to apply",
}

FR = {
    'tab.overview': "Aperçu",
    'tab.fans': "Ventilateurs",
    'tab.rgb': "Spark RGB",
    'tab.drivers': "Pilotes et firmware",

    'status.watching': "SURVEILLANCE",
    'status.crashed': "QUELQUE CHOSE A ÉCHOUÉ",
    'status.saving': "MOT DE PASSE ATTENDU",
    'status.saved': "FAIT",
    'status.failed': "ÉCHEC",
    'status.scanning': "RECHERCHE DES LUMIÈRES",
    'status.applying': "APPLICATION",
    'status.checking': "VÉRIFICATION LVFS",
    'status.updating': "MISE À JOUR DU FIRMWARE",

    'col.fan': "Ventilateur",
    'col.speed': "Vitesse",
    'col.duty': "Puissance",
    'col.control': "Contrôlé par",
    'col.device': "Appareil",
    'col.version': "Version",
    'col.state': "État",

    'tile.cpu': "CPU",
    'tile.gpu': "GPU",
    'tile.liquid': "Liquide",
    'tile.profile': "Ventilateurs",
    'tile.no_liquid': "pas de sonde",
    'profile.spark': "Spark, {n}",
    'profile.firmware': "Firmware",
    'overview.fans': "Ventilateurs et pompes",
    'overview.none': "Aucun ventilateur trouvé. Ceux de la carte mère apparaissent une fois "
                     "son pilote de sondes chargé.",
    'mode.spark': "Spark Controller",
    'mode.firmware': "Firmware (automatique)",
    'mode.readonly': "Firmware (lecture seule)",
    'mode.error': "Spark, mais en échec",
    'hint.board_driver': "Les connecteurs de ventilateurs de la carte mère ne sont pas encore "
                         "visibles. Spark charge leur pilote (nct6775) au démarrage : "
                         "redémarrez le PC une fois.",
    'hint.service_off': "Les courbes sont enregistrées, mais le service des ventilateurs ne "
                        "tourne pas. Les ventilateurs suivent leur propre contrôle.",

    'fans.list': "Ventilateurs",
    'fans.use_spark': "Spark contrôle ce ventilateur",
    'fans.source': "Température",
    'fans.fixed': "Puissance fixe",
    'fans.minimum': "Jamais sous",
    'fans.curve_help': "Glissez un point pour le déplacer. Cliquez dans le vide pour en "
                       "ajouter un. Double-cliquez un point pour l'enlever. Modifier un "
                       "préréglage en fait votre propre courbe. La ligne dorée est la "
                       "température actuelle.",
    'fans.apply': "Appliquer",
    'fans.revert': "Annuler",
    'fans.hand_back': "Rendre tous les ventilateurs",
    'fans.unsaved': "Changements pas encore appliqués. Appliquer demande votre mot de passe "
                    "une fois.",
    'fans.applied': "Appliqué. Spark contrôle {n} ventilateur(s) et les rend en s'arrêtant.",
    'fans.applied_none': "Appliqué. Chaque ventilateur est revenu à son propre contrôle.",
    'fans.handed_back': "Chaque ventilateur est revenu à son propre contrôle.",
    'fans.failed': "Non appliqué : {error}",
    'fans.cancelled': "La demande de mot de passe a été annulée.",
    'fans.none': "Aucun ventilateur trouvé.",
    'fans.read_only': "Ce ventilateur se lit mais ne se règle pas : sa puce n'a pas de "
                      "contrôle de puissance utilisable par Spark.",
    'fans.live': "{rpm}  ·  {duty}  ·  {mode}  ·  {temp}",

    'preset.quiet': "Silencieux",
    'preset.balanced': "Équilibré",
    'preset.performance': "Performance",
    'preset.fixed': "Fixe",
    'source.cpu': "CPU",
    'source.gpu': "GPU",
    'source.liquid': "Liquide",
    'source.max': "Le plus chaud",

    'rgb.devices': "Lumières",
    'rgb.rescan': "Chercher à nouveau",
    'rgb.scanning': "Recherche des lumières...",
    'rgb.none': "Aucune lumière contrôlable trouvée.",
    'rgb.effect': "Effet",
    'rgb.colour': "Couleur",
    'rgb.pick': "Autre...",
    'rgb.speed': "Vitesse",
    'rgb.apply': "Appliquer",
    'rgb.apply_all': "Appliquer à tout",
    'rgb.off': "Éteindre",
    'rgb.applied': "Appliqué à {n} appareil(s) et enregistré. Réappliqué à l'ouverture de "
                   "session.",
    'rgb.is_off': "Lumières éteintes, et elles le restent à l'ouverture de session.",
    'rgb.failed': "Échec : {errors}",
    'rgb.note': "Les contrôleurs USB comme NZXT passent par liquidctl. La carte mère, les "
                "souris, claviers et la mémoire passent par OpenRGB. Un effet qu'un appareil "
                "n'a pas est remplacé par le plus proche.",
    'effect.static': "Fixe",
    'effect.breathing': "Respiration",
    'effect.fade': "Fondu",
    'effect.spectrum': "Spectre",
    'effect.off': "Éteint",
    'speed.slow': "Lent",
    'speed.normal': "Normal",
    'speed.fast': "Rapide",

    'drivers.firmware': "Firmware des appareils",
    'drivers.firmware_note': "Depuis LVFS, via fwupd. L'installation demande votre mot de "
                             "passe, et certaines mises à jour se terminent au prochain "
                             "redémarrage.",
    'drivers.check': "Chercher des mises à jour",
    'drivers.install': "Installer les mises à jour",
    'drivers.no_fwupd': "fwupd n'est pas installé.",
    'drivers.reading': "Lecture des appareils...",
    'drivers.checking': "Interrogation de LVFS...",
    'drivers.installing': "Installation. N'éteignez pas le PC.",
    'drivers.installed': "Terminé. {detail}",
    'drivers.failed': "Échec : {error}",
    'drivers.n_updates': "{n} mise(s) à jour disponible(s).",
    'drivers.none_pending': "Rien à mettre à jour.",
    'drivers.update_to': "Mise à jour vers {version}",
    'drivers.up_to_date': "À jour",
    'drivers.not_updatable': "Pas modifiable ici",
    'drivers.release': "Version {version}",
    'drivers.reboot': "Demande un redémarrage pour se terminer.",
    'drivers.system': "Pilotes du système",
    'drivers.system_note': "Mis à jour avec l'image du système, via Spark Update.",
    'drivers.kernel': "Noyau",
    'drivers.mesa': "Mesa (graphismes)",
    'drivers.gpu_firmware': "Firmware GPU (amdgpu)",
    'drivers.unknown': "inconnu",
    'drivers.bios': "BIOS",
    'drivers.board': "Carte mère",
    'drivers.bios_version': "Version du BIOS",
    'drivers.bios_date': "Date du BIOS",
    'drivers.bios_vendor': "Éditeur du BIOS",
    'drivers.bios_note': "Spark montre la version du BIOS sans la flasher. Si LVFS liste "
                         "votre carte plus haut, mettez-la à jour là. Sinon, utilisez l'outil "
                         "du fabricant de la carte.",

    'cli.rgb_applied': "RGB : appliqué à {n} appareil(s)",
    'cli.rgb_none': "RGB : rien d'enregistré à appliquer",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
