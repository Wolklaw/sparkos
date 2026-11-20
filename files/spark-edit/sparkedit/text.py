"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # header and tabs
    'untitled': "Untitled",
    'untitled_n': "Untitled {n}",
    'tip.new': "New (Ctrl+N)",
    'tip.open': "Open (Ctrl+O)",
    'tip.save': "Save (Ctrl+S)",
    'tip.find': "Find (Ctrl+F)",
    'tip.menu': "Menu",

    # menu
    'menu.new': "New",
    'menu.open': "Open…",
    'menu.recent': "Open recent",
    'menu.recent_empty': "Nothing yet",
    'menu.recent_clear': "Clear the list",
    'menu.save': "Save",
    'menu.save_as': "Save as…",
    'menu.save_admin': "Save as administrator…",
    'menu.reload': "Reload from disk",
    'menu.close': "Close tab",
    'menu.close_others': "Close other tabs",
    'menu.reopen_closed': "Reopen closed tab",
    'menu.copy_path': "Copy path",
    'menu.find': "Find",
    'menu.replace': "Replace",
    'menu.goto': "Go to line",
    'menu.comment': "Comment or uncomment lines",
    'menu.wrap': "Word wrap",
    'menu.zoom_in': "Zoom in",
    'menu.zoom_out': "Zoom out",
    'menu.zoom_reset': "Actual size",
    'menu.session': "Reopen last session at start",
    'menu.quit': "Quit",
    'menu.reopen_with': "Reopen with",
    'menu.save_with': "Save with",
    'menu.plain': "Plain text",

    # start screen
    'start.title': "Nothing open",
    'start.new': "New file",
    'start.open': "Open file",
    'start.recent': "Recent",
    'start.no_recent': "Files you open show up here.",

    # find bar
    'find.find': "Find",
    'find.replace': "Replace",
    'find.replace_one': "Replace",
    'find.replace_all': "Replace all",
    'find.case': "Case",
    'find.word': "Word",
    'find.regex': "Regex",
    'find.count': "{i} of {n}",
    'find.count_many': "{i} of {n}+",
    'find.none': "No matches",
    'find.bad': "Bad pattern: {why}",
    'find.replaced': "Replaced {n}.",
    'find.goto': "Go to line",
    'find.goto_hint': "line, or line:column (1-{n})",
    'find.loading': "Wait until the file has loaded",
    'find.enter': "Big file: press Enter to search",

    # status bar
    'status.position': "Ln {line}, Col {col}",
    'status.selected': "{n} selected",
    'status.wrap': "Wrap",
    'status.nowrap': "No wrap",
    'status.loading': "Loading {pct}%",
    'status.opening': "Opening {name}…",
    'status.saved': "Saved {path}",
    'status.saved_admin': "Saved {path} as administrator",
    'status.new_file': "New file: {path} is created when you save",
    'status.reloaded': "Reloaded {name}: it changed on disk",
    'status.read_only': "Read-only for you",
    'status.read_only_fs': "Read-only file system",
    'status.restored': "Brought back {n} unsaved file(s) from last time",
    'status.restored_changed': "{name} changed on disk since your unsaved edits; saving "
                               "overwrites it",
    'status.big': "{name} is {size}: word wrap is off for it",
    'status.huge': "{name} has lines over 20,000 characters: they show up to the window's edge "
                   "only. Find, Replace and Save still work on all of them",
    'status.mixed': "{name} has mixed line endings; it will be saved with {nl}",
    'status.encoding_set': "{name} will be saved as {enc}",
    'status.newline_set': "{name} will be saved with {nl} line endings",
    'status.no_comment': "{lang} has no line comments",
    'status.admin_wait': "Waiting for the password…",
    'status.copied': "Copied the path",

    # dialogs
    'button.save': "Save",
    'button.dont_save': "Don't save",
    'button.cancel': "Cancel",
    'button.open_anyway': "Open anyway",
    'button.overwrite': "Overwrite",
    'button.reload': "Reload",
    'button.keep': "Keep mine",
    'button.admin': "Save as administrator",
    'button.save_as': "Save as…",
    'button.utf8': "Save as UTF-8",
    'button.ok': "OK",
    'ask.unsaved_title': "Save changes?",
    'ask.unsaved': "{name} has changes that aren't saved.",
    'ask.binary_title': "Not a text file",
    'ask.binary': "{name} looks like a binary file (it has NUL bytes). Opening it as text "
                  "shows mostly noise, and saving it can damage it.",
    'ask.changed_title': "Changed on disk",
    'ask.changed': "{name} was changed by another program since you opened it.\n\n"
                   "Save anyway and overwrite those changes?",
    'ask.changed_reload': "{name} was changed by another program, and you have unsaved "
                          "edits here.\n\nReload it from disk and lose your edits?",
    'ask.denied_title': "You can't write this file",
    'ask.denied': "{path} belongs to the system or another user.\n\nSave as administrator "
                  "asks for your password and writes it with root rights.",
    'ask.denied_no_pkexec': "{path} belongs to the system or another user, and pkexec "
                            "isn't installed, so it can't be saved as administrator.",
    'ask.rofs_title': "Read-only file system",
    'ask.rofs': "{path} is on a read-only file system, so nobody can change it, not even "
                "the administrator. On SparkOS everything under /usr is part of the image; "
                "settings go in /etc or your home folder.\n\nSave a copy somewhere else?",
    'ask.encode_title': "Can't save in {enc}",
    'ask.encode': "Line {line}, column {col} has “{char}”, which {enc} can't hold.\n\n"
                  "Save the file as UTF-8 instead?",
    'ask.error_title': "Couldn't save",
    'ask.error': "{path}\n\n{why}",
    'ask.open_error_title': "Couldn't open",
    'ask.open_error': "{path}\n\n{why}",
    'ask.reopen_dirty_title': "Reopen with another encoding?",
    'ask.reopen_dirty': "Reopening {name} as {enc} loses the changes you haven't saved.",
    'ask.admin_failed': "Saving as administrator didn't work:\n\n{why}",
    'error.is_folder': "That's a folder, not a file",
    'error.cancelled': "Cancelled",
}

FR = {
    # header and tabs
    'untitled': "Sans titre",
    'untitled_n': "Sans titre {n}",
    'tip.new': "Nouveau (Ctrl+N)",
    'tip.open': "Ouvrir (Ctrl+O)",
    'tip.save': "Enregistrer (Ctrl+S)",
    'tip.find': "Rechercher (Ctrl+F)",
    'tip.menu': "Menu",

    # menu
    'menu.new': "Nouveau",
    'menu.open': "Ouvrir…",
    'menu.recent': "Ouvrir un fichier récent",
    'menu.recent_empty': "Rien pour l'instant",
    'menu.recent_clear': "Vider la liste",
    'menu.save': "Enregistrer",
    'menu.save_as': "Enregistrer sous…",
    'menu.save_admin': "Enregistrer en administrateur…",
    'menu.reload': "Recharger depuis le disque",
    'menu.close': "Fermer l'onglet",
    'menu.close_others': "Fermer les autres onglets",
    'menu.reopen_closed': "Rouvrir l'onglet fermé",
    'menu.copy_path': "Copier le chemin",
    'menu.find': "Rechercher",
    'menu.replace': "Remplacer",
    'menu.goto': "Aller à la ligne",
    'menu.comment': "Commenter ou décommenter les lignes",
    'menu.wrap': "Retour à la ligne",
    'menu.zoom_in': "Zoom avant",
    'menu.zoom_out': "Zoom arrière",
    'menu.zoom_reset': "Taille réelle",
    'menu.session': "Rouvrir la dernière session au démarrage",
    'menu.quit': "Quitter",
    'menu.reopen_with': "Rouvrir avec",
    'menu.save_with': "Enregistrer avec",
    'menu.plain': "Texte brut",

    # start screen
    'start.title': "Rien d'ouvert",
    'start.new': "Nouveau fichier",
    'start.open': "Ouvrir un fichier",
    'start.recent': "Récents",
    'start.no_recent': "Les fichiers que vous ouvrez s'affichent ici.",

    # find bar
    'find.find': "Rechercher",
    'find.replace': "Remplacer",
    'find.replace_one': "Remplacer",
    'find.replace_all': "Tout remplacer",
    'find.case': "Casse",
    'find.word': "Mot",
    'find.regex': "Regex",
    'find.count': "{i} sur {n}",
    'find.count_many': "{i} sur {n}+",
    'find.none': "Aucun résultat",
    'find.bad': "Motif invalide : {why}",
    'find.replaced': "{n} remplacé(s).",
    'find.goto': "Aller à la ligne",
    'find.goto_hint': "ligne, ou ligne:colonne (1-{n})",
    'find.loading': "Attendez que le fichier soit chargé",
    'find.enter': "Gros fichier : appuyez sur Entrée pour chercher",

    # status bar
    'status.position': "Ln {line}, Col {col}",
    'status.selected': "{n} sélectionné(s)",
    'status.wrap': "Retour à la ligne",
    'status.nowrap': "Sans retour",
    'status.loading': "Chargement {pct} %",
    'status.opening': "Ouverture de {name}…",
    'status.saved': "{path} enregistré",
    'status.saved_admin': "{path} enregistré en administrateur",
    'status.new_file': "Nouveau fichier : {path} sera créé à l'enregistrement",
    'status.reloaded': "{name} rechargé : il a changé sur le disque",
    'status.read_only': "Lecture seule pour vous",
    'status.read_only_fs': "Système de fichiers en lecture seule",
    'status.restored': "{n} fichier(s) non enregistré(s) récupéré(s) de la dernière fois",
    'status.restored_changed': "{name} a changé sur le disque depuis vos modifications non "
                               "enregistrées; l'enregistrer remplace cette version",
    'status.big': "{name} fait {size} : le retour à la ligne est désactivé pour lui",
    'status.huge': "{name} a des lignes de plus de 20 000 caractères : elles s'affichent "
                   "seulement jusqu'au bord de la fenêtre. Rechercher, Remplacer et Enregistrer "
                   "les traitent quand même en entier",
    'status.mixed': "{name} mélange les fins de ligne; il sera enregistré avec {nl}",
    'status.encoding_set': "{name} sera enregistré en {enc}",
    'status.newline_set': "{name} sera enregistré avec des fins de ligne {nl}",
    'status.no_comment': "{lang} n'a pas de commentaires de ligne",
    'status.admin_wait': "En attente du mot de passe…",
    'status.copied': "Chemin copié",

    # dialogs
    'button.save': "Enregistrer",
    'button.dont_save': "Ne pas enregistrer",
    'button.cancel': "Annuler",
    'button.open_anyway': "Ouvrir quand même",
    'button.overwrite': "Remplacer",
    'button.reload': "Recharger",
    'button.keep': "Garder ma version",
    'button.admin': "Enregistrer en administrateur",
    'button.save_as': "Enregistrer sous…",
    'button.utf8': "Enregistrer en UTF-8",
    'button.ok': "OK",
    'ask.unsaved_title': "Enregistrer les modifications?",
    'ask.unsaved': "{name} a des modifications non enregistrées.",
    'ask.binary_title': "Ce n'est pas un fichier texte",
    'ask.binary': "{name} semble être un fichier binaire (il contient des octets NUL). L'ouvrir "
                  "comme texte affiche surtout du bruit, et l'enregistrer peut l'abîmer.",
    'ask.changed_title': "Modifié sur le disque",
    'ask.changed': "{name} a été modifié par un autre programme depuis que vous l'avez "
                   "ouvert.\n\nEnregistrer quand même et écraser ces modifications?",
    'ask.changed_reload': "{name} a été modifié par un autre programme, et vous avez des "
                          "modifications non enregistrées ici.\n\nLe recharger depuis le disque "
                          "et perdre vos modifications?",
    'ask.denied_title': "Vous ne pouvez pas écrire dans ce fichier",
    'ask.denied': "{path} appartient au système ou à un autre utilisateur.\n\nEnregistrer en "
                  "administrateur demande votre mot de passe et l'écrit avec les droits root.",
    'ask.denied_no_pkexec': "{path} appartient au système ou à un autre utilisateur, et pkexec "
                            "n'est pas installé, alors il ne peut pas être enregistré en "
                            "administrateur.",
    'ask.rofs_title': "Système de fichiers en lecture seule",
    'ask.rofs': "{path} est sur un système de fichiers en lecture seule : personne ne peut le "
                "modifier, pas même l'administrateur. Sur SparkOS, tout ce qui est sous /usr "
                "fait partie de l'image; les réglages vont dans /etc ou dans votre dossier "
                "personnel.\n\nEnregistrer une copie ailleurs?",
    'ask.encode_title': "Impossible d'enregistrer en {enc}",
    'ask.encode': "La ligne {line}, colonne {col} contient « {char} », que {enc} ne peut pas "
                  "représenter.\n\nEnregistrer plutôt le fichier en UTF-8?",
    'ask.error_title': "Enregistrement impossible",
    'ask.error': "{path}\n\n{why}",
    'ask.open_error_title': "Ouverture impossible",
    'ask.open_error': "{path}\n\n{why}",
    'ask.reopen_dirty_title': "Rouvrir avec un autre encodage?",
    'ask.reopen_dirty': "Rouvrir {name} en {enc} fait perdre les modifications non "
                        "enregistrées.",
    'ask.admin_failed': "L'enregistrement en administrateur n'a pas fonctionné :\n\n{why}",
    'error.is_folder': "C'est un dossier, pas un fichier",
    'error.cancelled': "Annulé",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
