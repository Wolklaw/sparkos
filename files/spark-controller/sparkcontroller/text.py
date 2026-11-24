"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    'tab.overview': "Overview",
    'tab.fans': "Fans",
    'tab.rgb': "Spark RGB",
    'tab.mouse': "Mouse",
    'tab.pads': "Pads",
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

    'mouse.mice': "Mice",
    'mouse.scanning': "Looking for mice...",
    'mouse.rescan': "Look again",
    'mouse.none': "No supported gaming mouse found. Plug one in (or its receiver). Spark talks to "
                  "the mice libratbag supports, which includes many Logitech, Razer, SteelSeries "
                  "and Roccat models.",
    'mouse.no_daemon': "ratbagd, the service that talks to gaming mice, did not answer. Look "
                       "again in a moment.",
    'mouse.no_gio': "Mouse settings need PyGObject (python3-gobject), which is not installed.",
    'mouse.denied': "This account isn't allowed to talk to ratbagd. Only the person logged in at "
                    "the PC can change mouse settings.",
    'mouse.busy': "The mouse is busy. Close any other program that configures it, then try "
                  "again.",
    'mouse.failed': "Mouse settings failed: {error}",
    'mouse.profile_n': "Profile {n}",
    'mouse.profile_off': "Profile {n} (off)",
    'mouse.profiles': "Onboard profiles",
    'mouse.active_now': "In use on the mouse: profile {n}.",
    'mouse.active_next': "In use on the mouse after Apply: profile {n}.",
    'mouse.use_profile': "Use this profile",
    'mouse.in_use': "In use",
    'mouse.profile_is_off': "This profile is switched off on the mouse.",
    'mouse.slots': "DPI slots",
    'mouse.slot_n': "Slot {n}",
    'mouse.dpi': "{dpi} DPI",
    'mouse.on': "On",
    'mouse.active': "Active",
    'mouse.default': "Default",
    'mouse.keep_on': "The active and the default slot have to stay on, and one slot has to be "
                     "left on. Make another slot active or default first.",
    'mouse.rate': "Report rate",
    'mouse.hz': "{hz} Hz",
    'mouse.warn_off': "The mouse is set to {dpi} DPI on slot {slot}, which is switched off. "
                      "That is very slow. Use {suggest} DPI?",
    'mouse.warn_low': "The mouse is set to {dpi} DPI, which is very slow. Use {suggest} DPI?",
    'mouse.fix': "Use {dpi} DPI",
    'mouse.apply': "Apply",
    'mouse.revert': "Undo changes",
    'mouse.unsaved': "Changes not applied yet. Nothing has been sent to the mouse.",
    'mouse.applied': "Saved on the mouse.",
    'mouse.applied_unread': "Sent to the mouse, but it could not be read back to check.",
    'mouse.not_kept': "The mouse did not keep {n} change(s). What it holds now is shown.",
    'mouse.apply_failed': "Not applied: {error}",
    'mouse.note': "Nothing is sent to the mouse until you press Apply. Apply saves the settings "
                  "in the mouse's own memory, so they also hold on Windows and in other "
                  "programs. Remapping buttons isn't here yet.",
    'mouse.bad_profile': "Pick an active profile that is switched on.",
    'mouse.bad_rate': "Profile {n}: {rate} Hz is not a rate this mouse supports.",
    'mouse.bad_dpi': "Profile {n}, slot {slot}: {dpi} DPI is not a value this mouse supports.",
    'mouse.no_slot_on': "Profile {n}: leave at least one slot on.",
    'mouse.active_off': "Profile {n}: slot {slot} is the active one, so it has to stay on.",
    'mouse.default_off': "Profile {n}: slot {slot} is the default one, so it has to stay on.",
    'status.mouse_scanning': "LOOKING FOR MICE",

    'status.pads_in': "CONTROLLER CONNECTED",
    'status.pads_out': "CONTROLLER GONE",
    'status.rumble': "RUMBLE",

    'pads.list': "Game controllers",
    'pads.col_name': "Controller",
    'pads.col_link': "Connection",
    'pads.col_battery': "Battery",
    'pads.col_access': "Access",
    'pads.usb': "USB",
    'pads.bluetooth': "Bluetooth",
    'pads.virtual': "Virtual",
    'pads.other': "Other",
    'pads.ready': "Ready",
    'pads.blocked': "Blocked",
    'pads.no_battery': "--",
    'pads.none': "No controller found. Plug one in or switch one on; it shows up here by "
                 "itself.",
    'pads.connected': "Connected: {name}",
    'pads.gone': "Disconnected: {name}",
    'pads.virtual_note': "A virtual pad is made by a program, usually Steam Input, which copies "
                         "your real controller for games. Test the real one.",
    'pads.no_access': "This account can't read this controller, so the tester can't show it. "
                      "Normally the system lets whoever sits at the PC use a controller (a udev "
                      "rule with the uaccess tag); there is none for this model. To allow it "
                      "yourself, add this account to the input group: sudo usermod -aG input "
                      "$USER, then log out and in. That group can read every keyboard too, so "
                      "it is a trade.",
    'pads.press': "Press a button or move a stick.",
    'pads.tester': "Tester",
    'pads.left': "Left stick",
    'pads.right': "Right stick",
    'pads.stick_n': "Stick {n}",
    'pads.stick': "x {x}  y {y}  {mag} %  deadzone {flat} %",
    'pads.axes_note': "Sticks and triggers are told apart by where they rest, and numbered by "
                      "the kernel's axis order. A pad that numbers them oddly still shows every "
                      "axis.",
    'pads.measure': "Measure rest drift",
    'pads.measuring': "Leave the sticks alone... {n}",
    'pads.drift': "Drift at rest: {values}. A deadzone just above it hides it in a game.",
    'pads.drift_item': "{name} {pct} % (deadzone {dz} %)",
    'pads.rumble_heavy': "Heavy motor",
    'pads.rumble_light': "Light motor",
    'pads.rumble_none': "No rumble the system can drive on this controller.",
    'pads.rumble_blocked': "Rumble needs write access to the controller, and this account has "
                           "none.",
    'pads.rumble_failed': "Rumble failed: {error}",
    'pads.firmware': "Controller firmware",
    'pads.firmware_note': "Through fwupd, like the other devices, and only what fwupd supports: "
                          "its 8BitDo plugin knows a short list of USB models. Nothing is "
                          "flashed unless you press Install on a controller and confirm.",
    'pads.fw_known': "{name}: fwupd has a plugin for this model ({plugin}).",
    'pads.fw_unknown': "{name}: fwupd doesn't support this model (USB id {id}), so there is "
                       "nothing to update from here. Use the maker's own updater.",
    'pads.fw_bluetooth': "{name}: connected by Bluetooth. fwupd updates controllers over USB "
                         "only; plug it in with a cable to check.",
    'pads.fw_listed': "{n} controller(s) in fwupd's list.",
    'pads.fw_none_listed': "fwupd lists no controller right now.",
    'pads.fw_install': "Install update",
    'pads.fw_confirm': "Sure? Install now",
    'pads.fw_warn': "Keep it plugged in by cable and don't touch it while it updates. A failed "
                    "update can leave a controller dead until it is flashed again.",
    'pads.remap': "Remapping buttons isn't part of Spark Controller. Steam Input does it for "
                  "games started from Steam. A Spark remapper would be a service that sits "
                  "between the pad and every game, and it isn't built.",

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
    'tab.mouse': "Souris",
    'tab.pads': "Manettes",
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

    'mouse.mice': "Souris",
    'mouse.scanning': "Recherche des souris...",
    'mouse.rescan': "Chercher à nouveau",
    'mouse.none': "Aucune souris de jeu prise en charge. Branchez-en une (ou son récepteur). "
                  "Spark parle aux souris que libratbag prend en charge, dont beaucoup de "
                  "modèles Logitech, Razer, SteelSeries et Roccat.",
    'mouse.no_daemon': "ratbagd, le service qui parle aux souris de jeu, n'a pas répondu. "
                       "Cherchez à nouveau dans un instant.",
    'mouse.no_gio': "Les réglages de souris demandent PyGObject (python3-gobject), qui n'est "
                    "pas installé.",
    'mouse.denied': "Ce compte n'a pas le droit de parler à ratbagd. Seule la personne connectée "
                    "au PC peut changer les réglages de la souris.",
    'mouse.busy': "La souris est occupée. Fermez les autres programmes qui la configurent, puis "
                  "réessayez.",
    'mouse.failed': "Les réglages de la souris ont échoué : {error}",
    'mouse.profile_n': "Profil {n}",
    'mouse.profile_off': "Profil {n} (désactivé)",
    'mouse.profiles': "Profils de la souris",
    'mouse.active_now': "Utilisé sur la souris : profil {n}.",
    'mouse.active_next': "Utilisé sur la souris après Appliquer : profil {n}.",
    'mouse.use_profile': "Utiliser ce profil",
    'mouse.in_use': "Utilisé",
    'mouse.profile_is_off': "Ce profil est désactivé sur la souris.",
    'mouse.slots': "Paliers de DPI",
    'mouse.slot_n': "Palier {n}",
    'mouse.dpi': "{dpi} DPI",
    'mouse.on': "Actif",
    'mouse.active': "En cours",
    'mouse.default': "Par défaut",
    'mouse.keep_on': "Le palier en cours et le palier par défaut doivent rester activés, et un "
                     "palier doit rester activé. Choisissez d'abord un autre palier.",
    'mouse.rate': "Fréquence d'envoi",
    'mouse.hz': "{hz} Hz",
    'mouse.warn_off': "La souris est réglée à {dpi} DPI sur le palier {slot}, qui est désactivé. "
                      "C'est très lent. Utiliser {suggest} DPI ?",
    'mouse.warn_low': "La souris est réglée à {dpi} DPI, ce qui est très lent. Utiliser "
                      "{suggest} DPI ?",
    'mouse.fix': "Utiliser {dpi} DPI",
    'mouse.apply': "Appliquer",
    'mouse.revert': "Annuler les changements",
    'mouse.unsaved': "Changements pas encore appliqués. Rien n'a été envoyé à la souris.",
    'mouse.applied': "Enregistré sur la souris.",
    'mouse.applied_unread': "Envoyé à la souris, mais impossible de le relire pour vérifier.",
    'mouse.not_kept': "La souris n'a pas gardé {n} changement(s). Ce qu'elle contient "
                      "maintenant est affiché.",
    'mouse.apply_failed': "Pas appliqué : {error}",
    'mouse.note': "Rien n'est envoyé à la souris avant d'appuyer sur Appliquer. Appliquer "
                  "enregistre les réglages dans la mémoire de la souris elle-même, donc ils "
                  "tiennent aussi sous Windows et dans d'autres programmes. Le remappage des "
                  "boutons n'est pas encore là.",
    'mouse.bad_profile': "Choisissez un profil en cours qui est activé.",
    'mouse.bad_rate': "Profil {n} : {rate} Hz n'est pas une fréquence que cette souris prend "
                      "en charge.",
    'mouse.bad_dpi': "Profil {n}, palier {slot} : {dpi} DPI n'est pas une valeur que cette "
                     "souris prend en charge.",
    'mouse.no_slot_on': "Profil {n} : laissez au moins un palier activé.",
    'mouse.active_off': "Profil {n} : le palier {slot} est celui en cours, il doit rester "
                        "activé.",
    'mouse.default_off': "Profil {n} : le palier {slot} est celui par défaut, il doit rester "
                         "activé.",
    'status.mouse_scanning': "RECHERCHE DES SOURIS",

    'status.pads_in': "MANETTE BRANCHÉE",
    'status.pads_out': "MANETTE DÉBRANCHÉE",
    'status.rumble': "VIBRATION",

    'pads.list': "Manettes de jeu",
    'pads.col_name': "Manette",
    'pads.col_link': "Connexion",
    'pads.col_battery': "Pile",
    'pads.col_access': "Accès",
    'pads.usb': "USB",
    'pads.bluetooth': "Bluetooth",
    'pads.virtual': "Virtuelle",
    'pads.other': "Autre",
    'pads.ready': "Prête",
    'pads.blocked': "Bloqué",
    'pads.no_battery': "--",
    'pads.none': "Aucune manette trouvée. Branchez-en une ou allumez-en une; elle apparaît ici "
                 "toute seule.",
    'pads.connected': "Branchée : {name}",
    'pads.gone': "Débranchée : {name}",
    'pads.virtual_note': "Une manette virtuelle est créée par un programme, souvent Steam "
                         "Input, qui copie votre vraie manette pour les jeux. Testez la vraie.",
    'pads.no_access': "Ce compte ne peut pas lire cette manette, donc le testeur ne peut pas "
                      "l'afficher. Normalement, le système laisse la personne devant le PC "
                      "utiliser une manette (une règle udev avec l'étiquette uaccess); il n'y "
                      "en a pas pour ce modèle. Pour l'autoriser vous-même, ajoutez ce compte "
                      "au groupe input : sudo usermod -aG input $USER, puis fermez et rouvrez "
                      "la session. Ce groupe peut aussi lire tous les claviers, c'est un "
                      "compromis.",
    'pads.press': "Appuyez sur un bouton ou bougez un joystick.",
    'pads.tester': "Testeur",
    'pads.left': "Joystick gauche",
    'pads.right': "Joystick droit",
    'pads.stick_n': "Joystick {n}",
    'pads.stick': "x {x}  y {y}  {mag} %  zone morte {flat} %",
    'pads.axes_note': "Les joysticks et les gâchettes se distinguent par leur position au "
                      "repos, et sont numérotés selon l'ordre des axes du noyau. Une manette "
                      "qui les numérote autrement affiche quand même tous ses axes.",
    'pads.measure': "Mesurer la dérive au repos",
    'pads.measuring': "Ne touchez pas aux joysticks... {n}",
    'pads.drift': "Dérive au repos : {values}. Une zone morte juste au-dessus la cache dans "
                  "un jeu.",
    'pads.drift_item': "{name} {pct} % (zone morte {dz} %)",
    'pads.rumble_heavy': "Moteur lourd",
    'pads.rumble_light': "Moteur léger",
    'pads.rumble_none': "Cette manette n'a pas de vibration que le système peut piloter.",
    'pads.rumble_blocked': "La vibration demande l'accès en écriture à la manette, et ce "
                           "compte ne l'a pas.",
    'pads.rumble_failed': "La vibration a échoué : {error}",
    'pads.firmware': "Firmware des manettes",
    'pads.firmware_note': "Via fwupd, comme les autres appareils, et seulement ce que fwupd "
                          "prend en charge : son module 8BitDo connaît une courte liste de "
                          "modèles USB. Rien n'est flashé tant que vous n'appuyez pas sur "
                          "Installer pour une manette et ne confirmez pas.",
    'pads.fw_known': "{name} : fwupd a un module pour ce modèle ({plugin}).",
    'pads.fw_unknown': "{name} : fwupd ne prend pas ce modèle en charge (ID USB {id}), donc "
                       "rien à mettre à jour d'ici. Utilisez l'outil du fabricant.",
    'pads.fw_bluetooth': "{name} : connectée en Bluetooth. fwupd met les manettes à jour "
                         "seulement par USB; branchez-la avec un câble pour vérifier.",
    'pads.fw_listed': "{n} manette(s) dans la liste de fwupd.",
    'pads.fw_none_listed': "fwupd ne liste aucune manette pour le moment.",
    'pads.fw_install': "Installer la mise à jour",
    'pads.fw_confirm': "Sûr? Installer maintenant",
    'pads.fw_warn': "Gardez-la branchée par câble et n'y touchez pas pendant la mise à jour. "
                    "Une mise à jour ratée peut rendre une manette inutilisable jusqu'à un "
                    "nouveau flash.",
    'pads.remap': "Remapper les boutons ne fait pas partie de Spark Controller. Steam Input "
                  "le fait pour les jeux lancés depuis Steam. Un remappeur Spark serait un "
                  "service entre la manette et chaque jeu, et il n'est pas construit.",

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
