"""Every sentence Spark Update shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # the notification (the approved mockup)
    'notify.ready.title': "SparkOS updated",
    'notify.ready.body': "The new version is ready. It starts the next time you restart.",
    'notify.apps_ok': "Your apps are already up to date.",
    'notify.available.title': "SparkOS update available",
    'notify.available.body': "SparkOS {version} is ready to download. Open Spark Update to "
                             "get it.",
    'notify.available.body_no_version': "A new SparkOS version is ready to download. Open "
                                        "Spark Update to get it.",
    'notify.later': "Later",
    'notify.restart': "Restart",
    'notify.open': "Open",

    # status line under the title
    'status.reading': "READING",
    'status.up_to_date': "UP TO DATE",
    'status.ready': "UPDATE READY · RESTART TO USE IT",
    'status.available': "UPDATE AVAILABLE",
    'status.checking': "CHECKING",
    'status.downloading': "DOWNLOADING",
    'status.flatpak': "UPDATING APPS",
    'status.failed': "LAST CHECK FAILED",
    'status.rolled_back': "PREVIOUS VERSION AT NEXT RESTART",
    'status.held': "UP TO DATE · HOLDING BACK {version}",
    'status.no_image': "NOT RUNNING FROM AN IMAGE",
    'status.test_data': "TEST DATA",

    # panels
    'panel.this_pc': "This PC runs",
    'panel.next': "Next restart",
    'panel.changes_update': "What the update changes",
    'panel.changes_current': "What changed in this version",
    'panel.changes_rollback': "What rolling back changes",
    'panel.contents': "What's in this version",
    'panel.apps': "Apps (Flatpak)",
    'panel.checks': "Checks",

    'pc.version': "SparkOS {version}",
    'pc.built': "built {date}",
    'pc.image': "{image}",
    'pc.unknown': "Can't read the system status: {why}",
    'next.same': "The same version. Nothing waits for a restart.",
    'next.staged': "SparkOS {version}, downloaded and ready",
    'next.rollback': "SparkOS {version}, the previous version (you rolled back)",
    'next.pinned': "pinned",

    'changes.since': "Compared with {version}, the version before it on this PC.",
    'changes.update': "Compared with the version running now.",
    'changes.none': "Same versions of SparkOS's apps and drivers.",
    'changes.same': "{n} more unchanged",
    'changes.added': "new",
    'changes.removed': "removed",
    'changes.no_list': "{version} was built before SparkOS listed what's inside each version, "
                       "and its files can't be read here, so there's nothing to compare.",
    'changes.unreadable': "Can't read the files of {version} on this PC.",
    'changes.no_previous': "There's no earlier version on this PC to compare with.",
    'changes.from_files': "read from the version's files",
    'changes.notes_since': "What's new since {version}, the version you had before:",
    'changes.notes_update': "What's new in the update:",
    'changes.notes_rollback': "Rolling back undoes these:",
    'changes.versions': "Versions",
    'changes.no_notes': "No release notes for this version: it was built before SparkOS "
                        "wrote them. The versions below are what changed.",

    'apps.updated': "{n} updated {when}: {names}",
    'apps.none': "Up to date (checked {when}).",
    'apps.failed': "Couldn't update {when}: {why}",
    'apps.off': "Flatpak updates are off.",
    'apps.not_yet': "Not updated by Spark Update yet.",
    'apps.yours': "Yours",
    'apps.system': "System",

    'check.last': "Last check {when}.",
    'check.never': "Not checked yet.",
    'check.next': "Next check after {when}.",
    'check.off': "Automatic updates are off: it checks only when you click Check now.",
    'check.notify_only': "Notify only: it checks and tells you, and downloads nothing until "
                         "you click.",
    'check.postponed': "Waiting for a later hour: {why}.",
    'check.failed': "The last check failed: {why}",
    'check.held': "Holding back SparkOS {version} because you rolled back from it. Click "
                  "Check now to install it anyway.",
    'check.direct': "Background checks come with the SparkOS image; this copy checks only "
                    "when you click.",

    # buttons
    'btn.check': "Check now",
    'btn.download': "Download update",
    'btn.restart': "Restart to update",
    'btn.restart_plain': "Restart",
    'btn.rollback': "Roll back",
    'btn.undo_rollback': "Cancel roll back",
    'btn.settings': "Settings",
    'btn.log': "Log",
    'btn.back': "Back",
    'btn.save': "Save",
    'btn.cancel': "Cancel",

    # App updates (Spark Apps: signed app updates, no restart)
    'btn.apps': "App updates",
    'btn.apps_now': "Update now",
    'btn.use_builtin': "Use built-in version",
    'btn.use_live': "Use updated version",
    'apps.heading': "Spark apps",
    'apps.intro': "Spark apps get their own updates, signed by SparkOS, without a restart. "
                  "Restart an app to use its new version.",
    'apps.none': "No app takes live updates on this PC.",
    'apps.not_installed': "This copy of Spark Update isn't on a SparkOS image that has app "
                          "updates.",
    'apps.versions': "{version}, from the updates",
    'apps.versions_builtin': "{version}, built in",
    'apps.state.current': "Up to date",
    'apps.state.newer': "{version} is available",
    'apps.state.needs_os': "{version} needs a SparkOS update and a restart first",
    'apps.state.held': "Updates are off for this app: it uses the built-in version",
    'apps.state.error': "Last update failed: {why}",
    'apps.checked': "Last check {when}: {result}",
    'apps.result.ok': "done",
    'apps.result.offline': "no network",
    'apps.result.refused': "refused, not from SparkOS",
    'apps.result.failed': "some apps failed",
    'apps.never': "never checked",
    'msg.apps_working': "Looking for app updates...",
    'msg.apps_none': "Your apps are up to date.",
    'msg.apps_done': "Updated: {apps}. Restart those apps to use the new versions.",
    'msg.apps_failed': "App updates didn't finish: {why}",
    'msg.apps_switched': "{app} will use the {which} version the next time it starts.",
    'which.builtin': "built-in",
    'which.live': "updated",

    # messages
    'msg.checking': "Checking for a new SparkOS version...",
    'msg.check_started': "Checking. You can close this window; it carries on.",
    'msg.check_failed': "Couldn't start the check: {why}",
    'msg.up_to_date': "SparkOS is up to date.",
    'msg.staged': "SparkOS {version} is ready. It starts the next time you restart.",
    'msg.available': "SparkOS {version} is available.",
    'msg.failed': "The check failed: {why}",
    'msg.rolled_back': "The next restart starts SparkOS {version}. Nothing was deleted.",
    'msg.unrolled': "Roll back cancelled: the next restart starts the version running now.",
    'msg.rollback_failed': "Couldn't roll back: {why}",
    'msg.cancelled': "Cancelled: nothing changed.",
    'msg.saved': "Saved.",
    'msg.save_failed': "Couldn't save: {why}",
    'msg.restart_failed': "Couldn't restart. Restart from the menu instead.",
    'msg.test_data': "Not done: Spark Update is showing test data, not this PC.",

    # roll back dialog
    'rollback.title': "Roll back to the previous version?",
    'rollback.body': "The next time you restart, your PC starts SparkOS {old} (from {date}) "
                     "instead of {current}.\n\nNothing is deleted: your files, settings and "
                     "apps stay as they are, and {current} stays on the PC, so you can come "
                     "back to it with Cancel roll back.\n\nAutomatic updates will skip {current} "
                     "and wait for the next newer version; turn them off in Settings if you "
                     "want to stay on {old}.",
    'rollback.go': "Roll back",
    'rollback.restart_now': "Rolled back. Restart now to start SparkOS {version}?",
    'rollback.later': "Not now",
    'restart.title': "Restart now?",
    'restart.body': "Your apps are asked to close first; any that have unsaved work can stop "
                    "the restart.",

    # settings
    'set.system': "For everyone on this PC",
    'set.automatic': "Automatic updates",
    'set.automatic_note': "Check on its own, a few times a day. Never while a game runs, on "
                          "a metered connection or a low battery.",
    'set.every': "Check every",
    'set.hours': "{n} h",
    'set.mode': "When there's an update",
    'set.mode.stage': "Download it",
    'set.mode.notify': "Only tell me",
    'set.flatpak': "Update Flatpak apps too",
    'set.user': "Just for you",
    'set.notify': "Notify me when an update is ready",
    'set.remind': "After Later, remind me",
    'set.remind.24': "Next day",
    'set.remind.72': "In 3 days",
    'set.remind.168': "In a week",
    'set.admin_note': "Saving these asks for an administrator password.",
    'set.no_helper': "These come with the SparkOS image install; this copy can't change them.",
    'set.conf_warnings': "update.conf has lines it ignored: {lines}",

    'log.system': "Background checks",
    'log.user': "This account",
    'log.empty': "Nothing logged yet.",

    # dates (core.when, core.day)
    'when.never': "never",
    'when.today': "today {clock}",
    'when.yesterday': "yesterday {clock}",
    'when.date': "{month} {day} {clock}",
    'day.date': "{month} {day}, {year}",
    'months': "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",

    # why a background check waits (guard.py)
    'wait.game': "a game is running ({game})",
    'wait.metered': "the connection is metered",
    'wait.battery': "the battery is at {percent}% and not charging",

    # errors from the updater
    'err.no_flatpak': "flatpak isn't available",
    'err.no_status': "can't read the system status: {why}",
    'err.no_previous': "there is no previous version on this PC",

    # parts of the system in "What's in this version" (release.py ids)
    'platform.base': "Base system",
    'platform.kernel': "Linux kernel",
    'platform.mesa': "Mesa graphics drivers",
    'platform.flatpak': "Flatpak",
}

FR = {
    # the notification (the approved mockup)
    'notify.ready.title': "SparkOS est à jour",
    'notify.ready.body': "La nouvelle version est prête. Elle démarre au prochain redémarrage.",
    'notify.apps_ok': "Vos applications sont déjà à jour.",
    'notify.available.title': "Mise à jour de SparkOS disponible",
    'notify.available.body': "SparkOS {version} est prêt à télécharger. Ouvrez Spark Update "
                             "pour l'obtenir.",
    'notify.available.body_no_version': "Une nouvelle version de SparkOS est prête à "
                                        "télécharger. Ouvrez Spark Update pour l'obtenir.",
    'notify.later': "Plus tard",
    'notify.restart': "Redémarrer",
    'notify.open': "Ouvrir",

    # status line under the title
    'status.reading': "LECTURE",
    'status.up_to_date': "À JOUR",
    'status.ready': "MISE À JOUR PRÊTE · REDÉMARREZ POUR L'UTILISER",
    'status.available': "MISE À JOUR DISPONIBLE",
    'status.checking': "VÉRIFICATION",
    'status.downloading': "TÉLÉCHARGEMENT",
    'status.flatpak': "MISE À JOUR DES APPLICATIONS",
    'status.failed': "LA DERNIÈRE VÉRIFICATION A ÉCHOUÉ",
    'status.rolled_back': "VERSION PRÉCÉDENTE AU PROCHAIN REDÉMARRAGE",
    'status.held': "À JOUR · {version} MISE DE CÔTÉ",
    'status.no_image': "PAS DÉMARRÉ À PARTIR D'UNE IMAGE",
    'status.test_data': "DONNÉES DE TEST",

    # panels
    'panel.this_pc': "Ce PC utilise",
    'panel.next': "Prochain redémarrage",
    'panel.changes_update': "Ce que la mise à jour change",
    'panel.changes_current': "Ce qui a changé dans cette version",
    'panel.changes_rollback': "Ce que le retour en arrière change",
    'panel.contents': "Ce que contient cette version",
    'panel.apps': "Applications (Flatpak)",
    'panel.checks': "Vérifications",

    'pc.version': "SparkOS {version}",
    'pc.built': "compilé le {date}",
    'pc.image': "{image}",
    'pc.unknown': "Impossible de lire l'état du système : {why}",
    'next.same': "La même version. Rien n'attend un redémarrage.",
    'next.staged': "SparkOS {version}, téléchargé et prêt",
    'next.rollback': "SparkOS {version}, la version précédente (vous êtes revenu en arrière)",
    'next.pinned': "épinglée",

    'changes.since': "Comparé à {version}, la version précédente sur ce PC.",
    'changes.update': "Comparé à la version actuelle.",
    'changes.none': "Mêmes versions des applications et des pilotes de SparkOS.",
    'changes.same': "{n} autres inchangés",
    'changes.added': "nouveau",
    'changes.removed': "retiré",
    'changes.no_list': "{version} a été compilé avant que SparkOS liste le contenu de chaque "
                       "version, et ses fichiers ne peuvent pas être lus ici, alors il n'y a "
                       "rien à comparer.",
    'changes.unreadable': "Impossible de lire les fichiers de {version} sur ce PC.",
    'changes.no_previous': "Il n'y a pas de version antérieure sur ce PC pour comparer.",
    'changes.from_files': "lu dans les fichiers de la version",
    'changes.notes_since': "Les nouveautés depuis {version}, la version que vous aviez avant :",
    'changes.notes_update': "Les nouveautés de la mise à jour :",
    'changes.notes_rollback': "Revenir en arrière annule ceci :",
    'changes.versions': "Versions",
    'changes.no_notes': "Pas de notes pour cette version : elle a été compilée avant que "
                        "SparkOS les écrive. Les versions ci-dessous montrent ce qui a changé.",

    'apps.updated': "{n} mises à jour {when} : {names}",
    'apps.none': "À jour (vérifié {when}).",
    'apps.failed': "Mise à jour impossible {when} : {why}",
    'apps.off': "Les mises à jour Flatpak sont désactivées.",
    'apps.not_yet': "Pas encore mises à jour par Spark Update.",
    'apps.yours': "Les vôtres",
    'apps.system': "Système",

    'check.last': "Dernière vérification : {when}.",
    'check.never': "Pas encore vérifié.",
    'check.next': "Prochaine vérification : {when} ou après.",
    'check.off': "Les mises à jour automatiques sont désactivées : il vérifie seulement quand "
                 "vous cliquez sur Vérifier.",
    'check.notify_only': "Avertir seulement : il vérifie et vous avertit, et ne télécharge "
                         "rien tant que vous ne cliquez pas.",
    'check.postponed': "En attente d'une heure plus tard : {why}.",
    'check.failed': "La dernière vérification a échoué : {why}",
    'check.held': "SparkOS {version} est mise de côté parce que vous en êtes revenu en "
                  "arrière. Cliquez sur Vérifier pour l'installer quand même.",
    'check.direct': "Les vérifications en arrière-plan viennent avec l'image SparkOS; cette "
                    "copie vérifie seulement quand vous cliquez.",

    # buttons
    'btn.check': "Vérifier",
    'btn.download': "Télécharger",
    'btn.restart': "Redémarrer et installer",
    'btn.restart_plain': "Redémarrer",
    'btn.rollback': "Revenir en arrière",
    'btn.undo_rollback': "Annuler le retour",
    'btn.settings': "Réglages",
    'btn.log': "Journal",
    'btn.back': "Retour",
    'btn.save': "Enregistrer",
    'btn.cancel': "Annuler",

    # Mises à jour des apps (Spark Apps : mises à jour signées, sans redémarrage)
    'btn.apps': "Mises à jour d'apps",
    'btn.apps_now': "Mettre à jour",
    'btn.use_builtin': "Version d'origine",
    'btn.use_live': "Version à jour",
    'apps.heading': "Applications Spark",
    'apps.intro': "Les applications Spark reçoivent leurs propres mises à jour, signées par "
                  "SparkOS, sans redémarrage. Relancez une application pour utiliser sa "
                  "nouvelle version.",
    'apps.none': "Aucune application de ce PC ne reçoit de mises à jour en direct.",
    'apps.not_installed': "Cette copie de Spark Update n'est pas sur une image SparkOS qui "
                          "a les mises à jour d'apps.",
    'apps.versions': "{version}, reçue en mise à jour",
    'apps.versions_builtin': "{version}, d'origine",
    'apps.state.current': "À jour",
    'apps.state.newer': "{version} est disponible",
    'apps.state.needs_os': "{version} demande d'abord une mise à jour de SparkOS et un "
                           "redémarrage",
    'apps.state.held': "Mises à jour désactivées pour cette application : elle utilise la "
                       "version d'origine",
    'apps.state.error': "La dernière mise à jour a échoué : {why}",
    'apps.checked': "Dernière vérification {when} : {result}",
    'apps.result.ok': "terminée",
    'apps.result.offline': "pas de réseau",
    'apps.result.refused': "refusée, ne vient pas de SparkOS",
    'apps.result.failed': "certaines apps ont échoué",
    'apps.never': "jamais vérifié",
    'msg.apps_working': "Recherche de mises à jour d'apps...",
    'msg.apps_none': "Vos applications sont à jour.",
    'msg.apps_done': "Mises à jour : {apps}. Relancez ces applications pour utiliser les "
                     "nouvelles versions.",
    'msg.apps_failed': "Les mises à jour d'apps ne se sont pas terminées : {why}",
    'msg.apps_switched': "{app} utilisera la version {which} au prochain démarrage.",
    'which.builtin': "d'origine",
    'which.live': "à jour",

    # messages
    'msg.checking': "Recherche d'une nouvelle version de SparkOS...",
    'msg.check_started': "Vérification en cours. Vous pouvez fermer cette fenêtre; elle "
                         "continue.",
    'msg.check_failed': "Impossible de lancer la vérification : {why}",
    'msg.up_to_date': "SparkOS est à jour.",
    'msg.staged': "SparkOS {version} est prêt. Il démarre au prochain redémarrage.",
    'msg.available': "SparkOS {version} est disponible.",
    'msg.failed': "La vérification a échoué : {why}",
    'msg.rolled_back': "Le prochain redémarrage lance SparkOS {version}. Rien n'a été supprimé.",
    'msg.unrolled': "Retour en arrière annulé : le prochain redémarrage lance la version "
                    "actuelle.",
    'msg.rollback_failed': "Impossible de revenir en arrière : {why}",
    'msg.cancelled': "Annulé : rien n'a changé.",
    'msg.saved': "Enregistré.",
    'msg.save_failed': "Enregistrement impossible : {why}",
    'msg.restart_failed': "Impossible de redémarrer. Redémarrez plutôt à partir du menu.",
    'msg.test_data': "Rien de fait : Spark Update affiche des données de test, pas ce PC.",

    # roll back dialog
    'rollback.title': "Revenir à la version précédente?",
    'rollback.body': "Au prochain redémarrage, votre PC lancera SparkOS {old} (du {date}) au "
                     "lieu de {current}.\n\nRien n'est supprimé : vos fichiers, réglages et "
                     "applications restent comme ils sont, et {current} reste sur le PC, alors "
                     "vous pouvez y revenir avec Annuler le retour.\n\nLes mises à jour "
                     "automatiques sauteront {current} et attendront la prochaine version plus "
                     "récente; désactivez-les dans Réglages si vous voulez rester sur {old}.",
    'rollback.go': "Revenir en arrière",
    'rollback.restart_now': "C'est fait. Redémarrer maintenant pour lancer SparkOS {version}?",
    'rollback.later': "Pas maintenant",
    'restart.title': "Redémarrer maintenant?",
    'restart.body': "Vos applications doivent d'abord se fermer; celles qui ont du travail non "
                    "enregistré peuvent empêcher le redémarrage.",

    # settings
    'set.system': "Pour tout le monde sur ce PC",
    'set.automatic': "Mises à jour automatiques",
    'set.automatic_note': "Vérifier tout seul, quelques fois par jour. Jamais pendant un jeu, "
                          "sur une connexion limitée ou avec une batterie faible.",
    'set.every': "Vérifier toutes les",
    'set.hours': "{n} h",
    'set.mode': "Quand il y a une mise à jour",
    'set.mode.stage': "La télécharger",
    'set.mode.notify': "M'avertir seulement",
    'set.flatpak': "Mettre aussi à jour les applications Flatpak",
    'set.user': "Juste pour vous",
    'set.notify': "M'avertir quand une mise à jour est prête",
    'set.remind': "Après Plus tard, me le rappeler",
    'set.remind.24': "Le lendemain",
    'set.remind.72': "Dans 3 jours",
    'set.remind.168': "Dans une semaine",
    'set.admin_note': "Les enregistrer demande un mot de passe administrateur.",
    'set.no_helper': "Ces réglages viennent avec l'installation de l'image SparkOS; cette copie "
                     "ne peut pas les modifier.",
    'set.conf_warnings': "update.conf a des lignes ignorées : {lines}",

    'log.system': "Vérifications en arrière-plan",
    'log.user': "Ce compte",
    'log.empty': "Rien dans le journal pour l'instant.",

    # dates (core.when, core.day)
    'when.never': "jamais",
    'when.today': "aujourd'hui à {clock}",
    'when.yesterday': "hier à {clock}",
    'when.date': "le {day} {month} à {clock}",
    'day.date': "{day} {month} {year}",
    'months': "janv. févr. mars avr. mai juin juill. août sept. oct. nov. déc.",

    # why a background check waits (guard.py)
    'wait.game': "un jeu est ouvert ({game})",
    'wait.metered': "la connexion est limitée",
    'wait.battery': "la batterie est à {percent} % et ne charge pas",

    # errors from the updater
    'err.no_flatpak': "flatpak n'est pas disponible",
    'err.no_status': "impossible de lire l'état du système : {why}",
    'err.no_previous': "il n'y a pas de version précédente sur ce PC",

    # parts of the system in "What's in this version" (release.py ids)
    'platform.base': "Système de base",
    'platform.kernel': "Noyau Linux",
    'platform.mesa': "Pilotes graphiques Mesa",
    'platform.flatpak': "Flatpak",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
