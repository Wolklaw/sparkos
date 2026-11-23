"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # tab bar and menu
    'tab.shell': "Shell",
    'tip.new_tab': "New tab (Ctrl+Shift+T)",
    'tip.menu': "Menu",
    'tip.close_tab': "Close tab (Ctrl+Shift+W)",
    'menu.new_tab': "New tab",
    'menu.new_window': "New window",
    'menu.split_right': "Split side by side",
    'menu.split_down': "Split stacked",
    'menu.close_pane': "Close pane",
    'menu.close_tab': "Close tab",
    'menu.copy': "Copy",
    'menu.paste': "Paste",
    'menu.select_all': "Select all",
    'menu.find': "Find",
    'menu.zoom_in': "Zoom in",
    'menu.zoom_out': "Zoom out",
    'menu.zoom_reset': "Actual size",
    'menu.reset': "Clear and reset",
    'menu.settings': "Settings",
    'menu.open_link': "Open link",
    'menu.copy_link': "Copy link",
    'menu.open_folder': "Open folder",
    'menu.keys': "Keyboard shortcuts",

    # search bar
    'find.placeholder': "Find in scrollback",
    'find.case': "Case",
    'find.regex': "Regex",
    'find.prev': "Previous (Shift+Enter)",
    'find.next': "Next (Enter)",
    'find.none': "Not found",
    'find.bad_regex': "Not a valid pattern",

    # status in a pane
    'exited': "[{cmd} ended with code {code}]",
    'exited_signal': "[{cmd} stopped by signal {sig}]",
    'exited_hold': "Press Ctrl+Shift+W to close this tab.",
    'spawn_failed': "Couldn't start {cmd}: {why}",

    # close confirmation
    'ask.close_title': "Stop what's running?",
    'ask.close_one': "{what} is still running in this tab. Closing stops it.",
    'ask.close_pane': "{what} is still running in this pane. Closing stops it.",
    'ask.close_window': "Programs are still running in {n} panes: {what}. Closing the window "
                        "stops them.",
    'button.close': "Close",
    'button.cancel': "Cancel",
    'button.done': "Done",

    # settings
    'set.title': "Settings",
    'set.shell': "Shell",
    'set.shell_hint': "Empty: your login shell ({shell})",
    'set.start_dir': "Start in",
    'set.start_dir_hint': "Empty: the folder it was opened from (your home folder from the dock)",
    'set.font': "Font",
    'set.font_size': "Font size",
    'set.scrollback': "Scrollback lines",
    'set.copy_on_select': "Copy text when it's selected",
    'set.ctrl_c_v': "Ctrl+C copies the selection, Ctrl+V pastes",
    'set.confirm_close': "Ask before closing a running program",
    'set.cursor': "Cursor",
    'set.cursor.block': "Block",
    'set.cursor.ibeam': "Bar",
    'set.cursor.underline': "Underline",
    'set.cursor_blink': "Blinking cursor",
    'set.bell': "Bell",
    'set.bell.visual': "Flash",
    'set.bell.sound': "Sound",
    'set.bell.off': "Off",
    'set.glitch': "Glitch effect",
    'set.saved': "Saved. New tabs use it; open tabs get the look now.",
    'set.bad_shell': "{shell} isn't a program on this PC.",
    'set.bad_dir': "{path} isn't a folder.",

    # keyboard shortcuts
    'keys.title': "Keyboard shortcuts",
    'keys.list': (
        "Ctrl+Shift+T\tNew tab\n"
        "Ctrl+Shift+N\tNew window\n"
        "Ctrl+Shift+W\tClose pane or tab\n"
        "Ctrl+Shift+R\tSplit side by side\n"
        "Ctrl+Shift+D\tSplit stacked\n"
        "Alt+Arrows\tMove between panes\n"
        "Ctrl+PgUp / PgDn\tPrevious / next tab\n"
        "Alt+1 … 9\tGo to tab\n"
        "Ctrl+C / V\tCopy the selection / paste\n"
        "Ctrl+Shift+C / V\tCopy / paste\n"
        "Shift+Insert\tPaste\n"
        "Ctrl+Shift+A\tSelect all\n"
        "Ctrl+Shift+F\tFind\n"
        "Ctrl+Plus / Minus / 0\tZoom in / out / actual size\n"
        "Ctrl+Shift+K\tClear and reset\n"
        "Ctrl+Shift+,\tSettings\n"
        "Ctrl+click\tOpen a link or a file path\n"
        "Middle click\tPaste the selection"),
}

FR = {
    'tab.shell': "Shell",
    'tip.new_tab': "Nouvel onglet (Ctrl+Maj+T)",
    'tip.menu': "Menu",
    'tip.close_tab': "Fermer l'onglet (Ctrl+Maj+W)",
    'menu.new_tab': "Nouvel onglet",
    'menu.new_window': "Nouvelle fenêtre",
    'menu.split_right': "Diviser côte à côte",
    'menu.split_down': "Diviser l'un sur l'autre",
    'menu.close_pane': "Fermer le panneau",
    'menu.close_tab': "Fermer l'onglet",
    'menu.copy': "Copier",
    'menu.paste': "Coller",
    'menu.select_all': "Tout sélectionner",
    'menu.find': "Rechercher",
    'menu.zoom_in': "Agrandir",
    'menu.zoom_out': "Réduire",
    'menu.zoom_reset': "Taille réelle",
    'menu.reset': "Effacer et réinitialiser",
    'menu.settings': "Réglages",
    'menu.open_link': "Ouvrir le lien",
    'menu.copy_link': "Copier le lien",
    'menu.open_folder': "Ouvrir le dossier",
    'menu.keys': "Raccourcis clavier",

    'find.placeholder': "Rechercher dans l'historique",
    'find.case': "Casse",
    'find.regex': "Regex",
    'find.prev': "Précédent (Maj+Entrée)",
    'find.next': "Suivant (Entrée)",
    'find.none': "Introuvable",
    'find.bad_regex': "Motif invalide",

    'exited': "[{cmd} s'est terminé avec le code {code}]",
    'exited_signal': "[{cmd} arrêté par le signal {sig}]",
    'exited_hold': "Ctrl+Maj+W ferme cet onglet.",
    'spawn_failed': "Impossible de lancer {cmd} : {why}",

    'ask.close_title': "Arrêter ce qui tourne?",
    'ask.close_one': "{what} tourne encore dans cet onglet. Le fermer l'arrête.",
    'ask.close_pane': "{what} tourne encore dans ce panneau. Le fermer l'arrête.",
    'ask.close_window': "Des programmes tournent encore dans {n} panneaux : {what}. Fermer la "
                        "fenêtre les arrête.",
    'button.close': "Fermer",
    'button.cancel': "Annuler",
    'button.done': "Terminé",

    'set.title': "Réglages",
    'set.shell': "Shell",
    'set.shell_hint': "Vide : votre shell de connexion ({shell})",
    'set.start_dir': "Démarrer dans",
    'set.start_dir_hint': "Vide : le dossier d'où il a été ouvert (votre dossier personnel "
                          "depuis le dock)",
    'set.font': "Police",
    'set.font_size': "Taille de police",
    'set.scrollback': "Lignes d'historique",
    'set.copy_on_select': "Copier le texte dès qu'il est sélectionné",
    'set.ctrl_c_v': "Ctrl+C copie la sélection, Ctrl+V colle",
    'set.confirm_close': "Demander avant de fermer un programme en cours",
    'set.cursor': "Curseur",
    'set.cursor.block': "Bloc",
    'set.cursor.ibeam': "Barre",
    'set.cursor.underline': "Souligné",
    'set.cursor_blink': "Curseur clignotant",
    'set.bell': "Cloche",
    'set.bell.visual': "Clignotement",
    'set.bell.sound': "Son",
    'set.bell.off': "Aucune",
    'set.glitch': "Effet glitch",
    'set.saved': "Enregistré. Les nouveaux onglets l'utilisent; les onglets ouverts prennent "
                 "l'apparence tout de suite.",
    'set.bad_shell': "{shell} n'est pas un programme sur ce PC.",
    'set.bad_dir': "{path} n'est pas un dossier.",

    'keys.title': "Raccourcis clavier",
    'keys.list': (
        "Ctrl+Maj+T\tNouvel onglet\n"
        "Ctrl+Maj+N\tNouvelle fenêtre\n"
        "Ctrl+Maj+W\tFermer le panneau ou l'onglet\n"
        "Ctrl+Maj+R\tDiviser côte à côte\n"
        "Ctrl+Maj+D\tDiviser l'un sur l'autre\n"
        "Alt+Flèches\tPasser d'un panneau à l'autre\n"
        "Ctrl+PgPréc / PgSuiv\tOnglet précédent / suivant\n"
        "Alt+1 … 9\tAller à l'onglet\n"
        "Ctrl+C / V\tCopier la sélection / coller\n"
        "Ctrl+Maj+C / V\tCopier / coller\n"
        "Maj+Inser\tColler\n"
        "Ctrl+Maj+A\tTout sélectionner\n"
        "Ctrl+Maj+F\tRechercher\n"
        "Ctrl+Plus / Moins / 0\tAgrandir / réduire / taille réelle\n"
        "Ctrl+Maj+K\tEffacer et réinitialiser\n"
        "Ctrl+Maj+,\tRéglages\n"
        "Ctrl+clic\tOuvrir un lien ou un chemin de fichier\n"
        "Clic du milieu\tColler la sélection"),
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
