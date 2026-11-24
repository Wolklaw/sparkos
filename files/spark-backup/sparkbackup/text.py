"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    'tab.backups': "Backups",
    'tab.browse': "Browse",
    'tab.settings': "Settings",

    'status.ready': "READY",
    'status.crashed': "SOMETHING WENT WRONG",
    'status.password': "WAITING FOR PASSWORD",
    'status.done': "DONE",
    'status.failed': "FAILED",
    'status.working': "BACKING UP",
    'status.snapshot': "TAKING A SNAPSHOT",
    'status.copy': "COPYING TO THE DRIVE",
    'status.prune': "REMOVING OLD ONES",

    'col.date': "Backup",
    'col.here': "On this PC",
    'col.drive': "On the drive",
    'col.name': "Name",
    'col.size': "Size",
    'col.free': "Free",
    'col.type': "Type",
    'col.modified': "Modified",
    'col.state': "State",

    'tile.last': "Last backup",
    'tile.next': "Next backup",
    'tile.drive': "Drive",
    'tile.count': "Snapshots",
    'tile.never': "never",
    'tile.off': "off",
    'tile.no_drive': "none chosen",
    'tile.unplugged': "not plugged in",

    'banner.config': "The saved settings can't be read ({error}). Save new ones in Settings.",
    'banner.layout': "/home is not a Btrfs subvolume on this PC, so it can't be snapshotted. "
                     "Nothing is backed up.",
    'banner.failed': "The last backup failed: {error}",
    'banner.unplugged_last': "The last backup was made on this PC only: the drive was not "
                             "plugged in.",
    'banner.refused': "{drive} can't hold backups. {why}",
    'banner.off': "Automatic backups are off. Choose a schedule in Settings. Back up now "
                  "works once settings are saved.",

    'backups.none': "No snapshot yet. Save your settings, then press Back up now.",
    'backups.newest': "newest",
    'backups.running': "Working... {detail}",

    'btn.backup_now': "Back up now",
    'btn.remove': "Remove",
    'btn.remove_sure': "Click again to remove",
    'btn.browse': "Browse",
    'btn.up': "Up",
    'btn.restore_here': "Restore here",
    'btn.restore_to': "Restore to...",
    'btn.save': "Save and turn on",
    'btn.turn_off': "Turn off",

    'msg.cancelled': "Cancelled.",
    'msg.need_settings': "Save your settings first (Settings tab).",
    'msg.starting': "Starting...",
    'msg.started': "Started. It runs in the background; this list updates when it ends.",
    'msg.start_failed': "Could not start: {error}",
    'msg.removed': "Removed the snapshot of {name}.",
    'msg.remove_failed': "Not removed: {error}",

    'browse.snapshots': "Snapshots",
    'browse.help': "Pick a snapshot, open folders with a double-click, pick a file or folder, "
                   "then restore it. Restoring never replaces anything.",
    'browse.not_here': "This snapshot is only on the drive, and the drive is not plugged in.",
    'browse.cannot_read': "Can't open this folder: {error}",
    'browse.empty': "This folder is empty.",
    'browse.copying': "Copying...",
    'browse.restored': "Restored to {path}",
    'browse.restored_some': "Restored to {path}, but {n} item(s) could not be copied.",
    'browse.restore_failed': "Not restored: {error}",

    'settings.drive': "Drive for the copies",
    'settings.no_drive': "No copy on a drive (snapshots on this PC only)",
    'settings.drive_note': "Snapshots on this PC share the disk with /home: they protect against "
                           "a deleted file, not against a dead disk. A copy on another drive "
                           "does.",
    'settings.method_btrfs': "{name} is Btrfs: each copy is sent as a snapshot, and only the "
                             "changes after the first one.",
    'settings.method_rsync': "{name} holds plain folders: each copy is a full folder tree, "
                             "and unchanged files are shared with the one before. The first "
                             "copy takes a while.",
    'settings.schedule': "Schedule",
    'settings.daily': "Every day",
    'settings.weekly': "Every week",
    'settings.at': "at",
    'settings.keep': "How many to keep",
    'settings.keep_here': "On this PC",
    'settings.keep_drive': "On the drive",
    'settings.keep_note': "The oldest are removed first. The newest one, and the last one "
                          "copied to the drive, are always kept.",
    'settings.keep_number': "Keep counts must be whole numbers from 1 to 365.",
    'settings.password_note': "Saving asks for your password once. If the PC is off at the "
                              "set time, the backup runs at the next start.",
    'settings.invalid': "Not saved: {error}",
    'settings.cannot_use': "{drive} can't hold backups.",
    'settings.saved': "Saved. Automatic backups are on.",
    'settings.turned_off': "Saved. Automatic backups are off.",
    'settings.not_saved': "Not saved: {error}",

    'drive.ready': "Ready",
    'drive.ready_unmounted': "Ready (mounted only while it copies)",
    'drive.unplugged': "Not plugged in",
    'refuse.fat': "FAT drives can't hold file permissions or large files. Format it as "
                  "ext4 or Btrfs.",
    'refuse.system': "This is the system disk.",
    'refuse.readonly': "This drive is mounted read-only, so nothing can be copied to it.",
    'refuse.other': "Not supported.",

    'day.Mon': "Mon", 'day.Tue': "Tue", 'day.Wed': "Wed", 'day.Thu': "Thu",
    'day.Fri': "Fri", 'day.Sat': "Sat", 'day.Sun': "Sun",

    'cli.version': "Spark Backup {version}",
    'cli.last': "Last backup: {value}",
    'cli.next': "Next backup: {value}",
    'cli.snapshots': "Snapshots on this PC: {n}",
    'cli.drive': "Drive: {value}",
}

FR = {
    'tab.backups': "Sauvegardes",
    'tab.browse': "Parcourir",
    'tab.settings': "Réglages",

    'status.ready': "PRÊT",
    'status.crashed': "UN PROBLÈME EST SURVENU",
    'status.password': "MOT DE PASSE REQUIS",
    'status.done': "TERMINÉ",
    'status.failed': "ÉCHEC",
    'status.working': "SAUVEGARDE",
    'status.snapshot': "INSTANTANÉ EN COURS",
    'status.copy': "COPIE SUR LE DISQUE",
    'status.prune': "SUPPRESSION DES ANCIENNES",

    'col.date': "Sauvegarde",
    'col.here': "Sur ce PC",
    'col.drive': "Sur le disque",
    'col.name': "Nom",
    'col.size': "Taille",
    'col.free': "Libre",
    'col.type': "Type",
    'col.modified': "Modifié",
    'col.state': "État",

    'tile.last': "Dernière sauvegarde",
    'tile.next': "Prochaine",
    'tile.drive': "Disque",
    'tile.count': "Instantanés",
    'tile.never': "jamais",
    'tile.off': "désactivée",
    'tile.no_drive': "aucun choisi",
    'tile.unplugged': "débranché",

    'banner.config': "Les réglages enregistrés sont illisibles ({error}). Enregistrez-en de "
                     "nouveaux dans Réglages.",
    'banner.layout': "/home n'est pas un sous-volume Btrfs sur ce PC, on ne peut donc pas en "
                     "faire d'instantanés. Rien n'est sauvegardé.",
    'banner.failed': "La dernière sauvegarde a échoué : {error}",
    'banner.unplugged_last': "La dernière sauvegarde est restée sur ce PC : le disque n'était "
                             "pas branché.",
    'banner.refused': "{drive} ne peut pas contenir de sauvegardes. {why}",
    'banner.off': "Les sauvegardes automatiques sont désactivées. Choisissez un horaire dans "
                  "Réglages. Sauvegarder maintenant fonctionne une fois les réglages "
                  "enregistrés.",

    'backups.none': "Aucun instantané. Enregistrez vos réglages, puis appuyez sur Sauvegarder "
                    "maintenant.",
    'backups.newest': "le plus récent",
    'backups.running': "En cours... {detail}",

    'btn.backup_now': "Sauvegarder maintenant",
    'btn.remove': "Supprimer",
    'btn.remove_sure': "Cliquez encore pour supprimer",
    'btn.browse': "Parcourir",
    'btn.up': "Monter",
    'btn.restore_here': "Restaurer ici",
    'btn.restore_to': "Restaurer vers...",
    'btn.save': "Enregistrer et activer",
    'btn.turn_off': "Désactiver",

    'msg.cancelled': "Annulé.",
    'msg.need_settings': "Enregistrez d'abord vos réglages (onglet Réglages).",
    'msg.starting': "Démarrage...",
    'msg.started': "Lancée. Elle tourne en arrière-plan; la liste se met à jour à la fin.",
    'msg.start_failed': "Impossible de la lancer : {error}",
    'msg.removed': "Instantané du {name} supprimé.",
    'msg.remove_failed': "Non supprimé : {error}",

    'browse.snapshots': "Instantanés",
    'browse.help': "Choisissez un instantané, ouvrez les dossiers d'un double-clic, choisissez "
                   "un fichier ou un dossier, puis restaurez-le. Restaurer ne remplace jamais "
                   "rien.",
    'browse.not_here': "Cet instantané n'est que sur le disque, qui n'est pas branché.",
    'browse.cannot_read': "Impossible d'ouvrir ce dossier : {error}",
    'browse.empty': "Ce dossier est vide.",
    'browse.copying': "Copie...",
    'browse.restored': "Restauré dans {path}",
    'browse.restored_some': "Restauré dans {path}, mais {n} élément(s) n'ont pas pu être "
                            "copiés.",
    'browse.restore_failed': "Non restauré : {error}",

    'settings.drive': "Disque pour les copies",
    'settings.no_drive': "Aucune copie sur un disque (instantanés sur ce PC seulement)",
    'settings.drive_note': "Les instantanés sur ce PC partagent le disque avec /home : ils "
                           "protègent d'un fichier supprimé, pas d'un disque mort. Une copie "
                           "sur un autre disque, si.",
    'settings.method_btrfs': "{name} est en Btrfs : chaque copie est envoyée comme un "
                             "instantané, et seulement les changements après la première.",
    'settings.method_rsync': "{name} contient des dossiers ordinaires : chaque copie est une "
                             "arborescence complète, et les fichiers inchangés sont partagés "
                             "avec la précédente. La première copie prend du temps.",
    'settings.schedule': "Horaire",
    'settings.daily': "Chaque jour",
    'settings.weekly': "Chaque semaine",
    'settings.at': "à",
    'settings.keep': "Combien en garder",
    'settings.keep_here': "Sur ce PC",
    'settings.keep_drive': "Sur le disque",
    'settings.keep_note': "Les plus anciennes sont supprimées en premier. La plus récente, et "
                          "la dernière copiée sur le disque, sont toujours gardées.",
    'settings.keep_number': "Les nombres à garder doivent être des entiers de 1 à 365.",
    'settings.password_note': "Enregistrer demande votre mot de passe une fois. Si le PC est "
                              "éteint à l'heure choisie, la sauvegarde se fait au prochain "
                              "démarrage.",
    'settings.invalid': "Non enregistré : {error}",
    'settings.cannot_use': "{drive} ne peut pas contenir de sauvegardes.",
    'settings.saved': "Enregistré. Les sauvegardes automatiques sont activées.",
    'settings.turned_off': "Enregistré. Les sauvegardes automatiques sont désactivées.",
    'settings.not_saved': "Non enregistré : {error}",

    'drive.ready': "Prêt",
    'drive.ready_unmounted': "Prêt (monté seulement pendant la copie)",
    'drive.unplugged': "Débranché",
    'refuse.fat': "Les disques FAT ne gardent pas les permissions et refusent les gros "
                  "fichiers. Formatez-le en ext4 ou en Btrfs.",
    'refuse.system': "C'est le disque du système.",
    'refuse.readonly': "Ce disque est monté en lecture seule, on ne peut rien y copier.",
    'refuse.other': "Non pris en charge.",

    'day.Mon': "Lun", 'day.Tue': "Mar", 'day.Wed': "Mer", 'day.Thu': "Jeu",
    'day.Fri': "Ven", 'day.Sat': "Sam", 'day.Sun': "Dim",

    'cli.version': "Spark Backup {version}",
    'cli.last': "Dernière sauvegarde : {value}",
    'cli.next': "Prochaine sauvegarde : {value}",
    'cli.snapshots': "Instantanés sur ce PC : {n}",
    'cli.drive': "Disque : {value}",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
