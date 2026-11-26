"""Every sentence the interface shows, in English and French. t('key', name=...) fills in the
blanks. The language comes from core.language(): SPARK_LANG=en|fr if set, else French when
LC_ALL, LC_MESSAGES or LANG (the first one set) starts with 'fr'."""

from .core import language

EN = {
    # window
    'empty.title': "No archive open",
    'empty.body': "Open a zip, tar, 7z, rar or iso file to see what's inside. In Spark Files, "
                  "right-click an archive for Extract here, or any files for Compress.",
    'button.open': "Open archive",
    'button.compress': "Compress files",
    'button.extract_all': "Extract all",
    'button.extract_selected': "Extract selected",
    'button.extract_to': "Extract to…",
    'button.cancel': "Cancel",
    'button.close': "Close",
    'button.show': "Show in folder",
    'button.ok': "OK",
    'button.replace': "Replace",
    'button.skip': "Skip",
    'button.keep_both': "Keep both",
    'col.name': "Name",
    'col.size': "Size",
    'col.modified': "Modified",
    'chip.password': "PASSWORD",
    'summary': "{files} files · {size} unpacked · {fmt}",
    'summary.read_with': "read with {backend}",
    'summary.parts': "{n} parts",
    'selected': "{n} selected",
    'dialog.archives': "Archives",
    'dialog.all_files': "All files",

    # status words (the coloured dot line, and the small window's title)
    'status.ready': "READY",
    'status.reading': "READING",
    'status.extracting': "EXTRACTING",
    'status.compressing': "COMPRESSING",
    'status.done': "DONE",
    'status.cancelled': "CANCELLED",
    'status.error': "ERROR",

    # progress
    'progress.reading': "Reading {name}…",
    'progress.files': "{done} of {total} files",
    'progress.bytes': "{done} of {total}",
    'progress.extract_title': "Extracting {name}",
    'progress.compress_title': "Compressing to {name}",
    'progress.cancelling': "Cancelling…",

    # making an archive
    'compress.as': "Compress {n} items as",
    'compress.with_password': "Protect with a password",
    'compress.password': "Password",
    'compress.again': "Same password again",
    'compress.kind_zip_any': "Zip that opens on any PC",
    'compress.kind_zip_strong': "Zip, strong protection",
    'compress.kind_7z': "7z, strong protection, names hidden",
    'compress.note_zip_any': "Weak protection (ZipCrypto): it can be cracked. Opens on any PC, "
                             "Windows included.",
    'compress.note_zip_strong': "AES-256. Windows needs 7-Zip or WinRAR to open it.",
    'compress.note_7z': "AES-256, and the file names are hidden too. Windows needs 7-Zip or "
                        "WinRAR to open it.",
    'compress.empty': "Type a password.",
    'compress.mismatch': "The two passwords aren't the same.",

    # password
    'password.title': "Password",
    'password.body': "{archive} is protected by a password.",
    'password.retry': "That password didn't work for {archive}. Try again.",
    'password.show': "show",

    # overwrite
    'overwrite.title': "Already there",
    'overwrite.body': "{name} already exists in this folder.",
    'overwrite.link': "{name} already exists in this folder (a link).",
    'overwrite.existing': "Existing:  {size}, {when}",
    'overwrite.new': "From archive:  {size}, {when}",
    'overwrite.all': "Do this for every file",

    # results
    'done.extracted': "Extracted {files} files to {folder}.",
    'done.extracted_selected': "Extracted {files} files to {folder}.",
    'done.compressed': "Made {name} ({size}).",
    'done.replaced': "{n} existing files replaced.",
    'done.skipped': "{n} files skipped (you chose Skip).",
    'done.problems': "Left out ({n}):",
    'done.cancelled_extract': "Cancelled. What this extraction had written was removed.",
    'done.cancelled_extract_replaced': "Cancelled. What this extraction had written was "
                                       "removed; {n} files it had already replaced stay "
                                       "replaced.",
    'done.cancelled_compress': "Cancelled. No archive was made.",

    # why something was left out
    'why.outside': "its path leads outside the folder",
    'why.link_out': "a link that points outside the folder",
    'why.special': "a device, pipe or socket",
    'why.refused': "the 7z command refused it as unsafe",
    'why.in_the_way': "a folder or link with that name is in the way",
    'why.failed': "the system refused: {why}",
    'why.unreadable': "couldn't read it: {why}",

    # errors
    'error.missing': "The file isn't there any more.",
    'error.not_archive': "This isn't an archive Spark Archive can read (zip, tar, 7z, rar, "
                         "iso, gz, bz2, xz or zst).",
    'error.unsupported': "Spark Archive can't read this archive: {detail}",
    'error.password': "This archive needs a password.",
    'error.damaged': "This archive is damaged or incomplete: {detail}",
    'error.missing_part': "This archive comes in several parts and {detail} is missing. Put "
                          "it in the same folder as the others, then try again.",
    'error.needs_unrar': "Password-protected RAR needs the unrar command (the unrar "
                         "package), and it isn't installed.",
    'error.needs_sevenzip': "This needs the 7z command (the 7zip package), and it isn't "
                            "installed.",
    'error.read_failed': "Couldn't read the archive: {detail}",
    'error.no_folder': "The folder {detail} isn't there.",
    'error.cant_write': "Can't write there: {detail}",
    'error.no_space': "Not enough free space on the disk.",
    'error.write_failed': "Writing failed: {detail}",
    'error.nothing': "There was nothing to compress.",
    'error.bug': "Something went wrong inside Spark Archive: {detail}. It's in the log.",
}

FR = {
    # fenêtre
    'empty.title': "Aucune archive ouverte",
    'empty.body': "Ouvrez un fichier zip, tar, 7z, rar ou iso pour voir ce qu'il contient. "
                  "Dans Spark Files, faites un clic droit sur une archive pour Extraire ici, ou "
                  "sur des fichiers pour Compresser.",
    'button.open': "Ouvrir une archive",
    'button.compress': "Compresser des fichiers",
    'button.extract_all': "Tout extraire",
    'button.extract_selected': "Extraire la sélection",
    'button.extract_to': "Extraire vers…",
    'button.cancel': "Annuler",
    'button.close': "Fermer",
    'button.show': "Afficher dans le dossier",
    'button.ok': "OK",
    'button.replace': "Remplacer",
    'button.skip': "Passer",
    'button.keep_both': "Garder les deux",
    'col.name': "Nom",
    'col.size': "Taille",
    'col.modified': "Modifié",
    'chip.password': "MOT DE PASSE",
    'summary': "{files} fichiers · {size} décompressés · {fmt}",
    'summary.read_with': "lu avec {backend}",
    'summary.parts': "{n} parties",
    'selected': "{n} sélectionnés",
    'dialog.archives': "Archives",
    'dialog.all_files': "Tous les fichiers",

    # mots d'état
    'status.ready': "PRÊT",
    'status.reading': "LECTURE",
    'status.extracting': "EXTRACTION",
    'status.compressing': "COMPRESSION",
    'status.done': "TERMINÉ",
    'status.cancelled': "ANNULÉ",
    'status.error': "ERREUR",

    # progression
    'progress.reading': "Lecture de {name}…",
    'progress.files': "{done} fichiers sur {total}",
    'progress.bytes': "{done} sur {total}",
    'progress.extract_title': "Extraction de {name}",
    'progress.compress_title': "Compression vers {name}",
    'progress.cancelling': "Annulation…",

    # créer une archive
    'compress.as': "Compresser {n} éléments en",
    'compress.with_password': "Protéger avec un mot de passe",
    'compress.password': "Mot de passe",
    'compress.again': "Retapez le mot de passe",
    'compress.kind_zip_any': "Zip qui s'ouvre sur n'importe quel PC",
    'compress.kind_zip_strong': "Zip, protection forte",
    'compress.kind_7z': "7z, protection forte, noms cachés",
    'compress.note_zip_any': "Protection faible (ZipCrypto) : elle peut être cassée. S'ouvre sur "
                             "n'importe quel PC, Windows compris.",
    'compress.note_zip_strong': "AES-256. Sur Windows, il faut 7-Zip ou WinRAR pour l'ouvrir.",
    'compress.note_7z': "AES-256, et les noms de fichiers sont cachés aussi. Sur Windows, il "
                        "faut 7-Zip ou WinRAR pour l'ouvrir.",
    'compress.empty': "Tapez un mot de passe.",
    'compress.mismatch': "Les deux mots de passe ne sont pas pareils.",

    # mot de passe
    'password.title': "Mot de passe",
    'password.body': "{archive} est protégé par un mot de passe.",
    'password.retry': "Ce mot de passe ne fonctionne pas pour {archive}. Réessayez.",
    'password.show': "afficher",

    # remplacer
    'overwrite.title': "Déjà là",
    'overwrite.body': "{name} existe déjà dans ce dossier.",
    'overwrite.link': "{name} existe déjà dans ce dossier (un lien).",
    'overwrite.existing': "Existant :  {size}, {when}",
    'overwrite.new': "De l'archive :  {size}, {when}",
    'overwrite.all': "Faire pareil pour tous les fichiers",

    # résultats
    'done.extracted': "{files} fichiers extraits dans {folder}.",
    'done.extracted_selected': "{files} fichiers extraits dans {folder}.",
    'done.compressed': "{name} créé ({size}).",
    'done.replaced': "{n} fichiers existants remplacés.",
    'done.skipped': "{n} fichiers passés (vous avez choisi Passer).",
    'done.problems': "Laissés de côté ({n}) :",
    'done.cancelled_extract': "Annulé. Ce que l'extraction avait écrit a été retiré.",
    'done.cancelled_extract_replaced': "Annulé. Ce que l'extraction avait écrit a été "
                                       "retiré; {n} fichiers déjà remplacés le restent.",
    'done.cancelled_compress': "Annulé. Aucune archive n'a été créée.",

    # pourquoi un élément a été laissé de côté
    'why.outside': "son chemin sort du dossier",
    'why.link_out': "un lien qui pointe hors du dossier",
    'why.special': "un périphérique, un tube ou un socket",
    'why.refused': "la commande 7z l'a refusé comme dangereux",
    'why.in_the_way': "un dossier ou un lien du même nom est dans le chemin",
    'why.failed': "le système a refusé : {why}",
    'why.unreadable': "lecture impossible : {why}",

    # erreurs
    'error.missing': "Le fichier n'est plus là.",
    'error.not_archive': "Ce n'est pas une archive que Spark Archive peut lire (zip, tar, 7z, "
                         "rar, iso, gz, bz2, xz ou zst).",
    'error.unsupported': "Spark Archive ne peut pas lire cette archive : {detail}",
    'error.password': "Cette archive demande un mot de passe.",
    'error.damaged': "Cette archive est endommagée ou incomplète : {detail}",
    'error.missing_part': "Cette archive est en plusieurs parties et {detail} manque. "
                          "Mettez-la dans le même dossier que les autres, puis réessayez.",
    'error.needs_unrar': "Les RAR protégés par un mot de passe demandent la commande unrar "
                         "(le paquet unrar), qui n'est pas installée.",
    'error.needs_sevenzip': "Il faut la commande 7z (le paquet 7zip), qui n'est pas "
                            "installée.",
    'error.read_failed': "Impossible de lire l'archive : {detail}",
    'error.no_folder': "Le dossier {detail} n'est pas là.",
    'error.cant_write': "Impossible d'écrire là : {detail}",
    'error.no_space': "Pas assez d'espace libre sur le disque.",
    'error.write_failed': "L'écriture a échoué : {detail}",
    'error.nothing': "Il n'y avait rien à compresser.",
    'error.bug': "Un problème est survenu dans Spark Archive : {detail}. C'est dans le "
                 "journal.",
}

TABLES = {'en': EN, 'fr': FR}

_T = TABLES.get(language(), EN)


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    try:
        return text.format(**kw) if kw else text
    except (KeyError, IndexError, ValueError):
        return text


def why(reason: str) -> str:
    """'failed:Permission denied' -> 'the system refused: Permission denied'"""
    key, _, detail = reason.partition(':')
    return t('why.' + key, why=detail) if detail else t('why.' + key)
