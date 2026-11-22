"""Every sentence the interface shows, in one place: English, and French for a French
desktop (LC_ALL, LC_MESSAGES or LANG starting with fr; SPARK_LANG=en|fr overrides it).
t('key', name=...) fills in the blanks."""

import os

EN = {
    # status line
    'status.ready': "READY",
    'status.looking': "LOOKING FOR SCANNERS",
    'status.connecting': "ASKING THE SCANNER",
    'status.previewing': "PREVIEW {pct}",
    'status.scanning': "SCANNING {pct}",
    'status.scanning_page': "SCANNING PAGE {n} {pct}",
    'status.saving': "SAVING {pages}",
    'status.reading': "READING TEXT {pages}",
    'status.cancelling': "STOPPING",
    'status.saved': "SAVED",
    'status.error': "SOMETHING WENT WRONG",
    'status.no_scanner': "NO SCANNER",

    # left column
    'label.scanner': "Scanner",
    'label.source': "Source",
    'label.resolution': "Resolution (dpi)",
    'label.colour': "Colour",
    'label.area': "Area",
    'label.save_as': "Save as",
    'label.pages': "Pages",
    'source.glass': "Glass",
    'source.feeder': "Feeder",
    'source.duplex': "Both sides",
    'mode.color': "Colour",
    'mode.gray': "Grey",
    'mode.bw': "B&W",
    'button.preview': "Preview",
    'button.scan': "Scan",
    'button.scan_feeder': "Scan feeder",
    'button.cancel': "Cancel",
    'button.save': "Save",
    'button.save_n': "Save {n} pages",
    'button.whole': "Whole glass",
    'button.clear': "Clear",
    'button.open_folder': "Open folder",
    'tip.look_again': "Look for scanners again",
    'tip.up': "Move page up (Alt+Up)",
    'tip.down': "Move page down (Alt+Down)",
    'tip.delete': "Delete page (Delete)",
    'tip.rotate_all': "Turn every page right (Ctrl+Shift+R)",
    'ocr.toggle': "Searchable text",
    'ocr.missing': "Searchable PDFs need tesseract, which isn't installed.",
    'ocr.no_lang': "tesseract has no English or French language data installed.",
    'ocr.pdf_only': "Searchable text is for PDFs.",
    'save.to': "To {folder}",

    # scanner list
    'scanner.looking': "Looking for scanners. Network scanners can take up to 30 seconds "
                       "to answer.",
    'scanner.none': "No scanner found. Check that it is switched on, and connected by USB "
                    "or on the same network as this PC. Then press the arrow to look again.",
    'scanner.no_sane': "SANE's scanimage isn't installed, so Spark Scan can't reach a "
                       "scanner. On Fedora: sudo dnf install sane-backends",
    'scanner.list_failed': "Looking for scanners failed: {detail}",
    'scanner.list_timeout': "No answer from the scanners after 40 seconds. Press the arrow "
                            "to look again.",
    'scanner.not_found': "{name} didn't answer. Check that it is on, then press the arrow to "
                         "look again.",
    'scanner.pick': "Pick a scanner",
    'scanner.last': "{name} (last used)",
    'scanner.network': "network",
    'scanner.usb': "USB",

    # middle
    'view.empty': "Press Preview to see what's on the glass,\nor Scan to scan it all.",
    'view.preview': "PREVIEW · DRAG TO PICK THE PART TO SCAN",
    'view.preview_crop': "PREVIEW · SCANNING THE MARKED PART ONLY",
    'view.page': "PAGE {n} OF {count} · {dpi} DPI · {w} × {h} MM",
    'view.feeder': "Put the pages in the feeder, then press Scan feeder.\nPreview works on "
                   "the glass only.",
    'area.whole': "Whole glass",
    'area.part': "{w} × {h} mm",
    'area.feeder': "Whole page (feeder)",

    # changing a page after the scan
    'tip.rotate_left': "Turn left (Ctrl+L)",
    'tip.rotate_right': "Turn right (Ctrl+R)",
    'tip.rotate_180': "Turn 180°",
    'edit.straighten': "Straighten",
    'edit.whiten': "Whiten paper",
    'edit.brightness': "Brightness",
    'edit.contrast': "Contrast",
    'edit.reset': "Reset",
    'edit.measuring': "Measuring the angle…",
    'edit.straightened': "Straightened by {angle}°.",
    'edit.straight': "Already straight.",
    'edit.no_lines': "No lines of text to straighten by; the page is left as it is.",
    'edit.bw': "Black and white pages have no brightness or contrast.",
    'edit.new_pages': "Straighten and Whiten paper stay on for the next pages.",
    'done.turned_all': "Turned {pages}.",

    # pages
    'pages.count': "{n} pages",
    'pages.one': "1 page",
    'pages.none': "No pages yet.",

    # results and errors
    'done.page': "Page {n} scanned.",
    'done.pages': "{n} pages scanned.",
    'done.feeder_partial': "Stopped after {n} pages.",
    'done.saved': "Saved {name}",
    'done.saved_n': "Saved {n} files: {name} …",
    'done.cancelled': "Cancelled.",
    'error.no_docs': "The feeder is empty. Put the pages in, face as the printer shows, "
                     "and scan again.",
    'error.jammed': "The paper is jammed. Clear it on the printer, then scan again.",
    'error.cover_open': "The scanner's cover is open. Close it and scan again.",
    'error.busy': "The scanner is busy, maybe printing or scanning for another program. "
                  "Wait for it, then scan again.",
    'error.denied': "This user isn't allowed to use the scanner.",
    'error.open_failed': "Couldn't connect to the scanner. Check that it is on, and still on "
                         "the network or plugged in.",
    'error.io': "The scanner stopped answering in the middle of the scan. Check its "
                "connection and scan again.",
    'error.no_mem': "The scanner ran out of memory. Try a lower resolution.",
    'error.options_timeout': "The scanner didn't answer. Check that it is on, then press the "
                             "arrow to look again.",
    'error.list_failed': "Looking for scanners failed.",
    'error.no_scanimage': "SANE's scanimage isn't installed.",
    'error.failed': "The scan failed.",
    'error.save': "Couldn't save: {detail}",
    'error.unexpected': "Unexpected error: {detail}",
    'error.detail': "Scanner said: {detail}",

    # dialogs
    'close.title': "Close Spark Scan?",
    'close.unsaved': "{pages} not saved yet. Close and lose them?",
    'clear.title': "Clear the pages?",
    'clear.confirm': "Remove {pages} from this document? Saved files are not touched.",

    # file names
    'file.scan': "Scan",
    'file.page': "page",
}

FR = {
    'status.ready': "PRÊT",
    'status.looking': "RECHERCHE DES NUMÉRISEURS",
    'status.connecting': "CONNEXION AU NUMÉRISEUR",
    'status.previewing': "APERÇU {pct}",
    'status.scanning': "NUMÉRISATION {pct}",
    'status.scanning_page': "NUMÉRISATION PAGE {n} {pct}",
    'status.saving': "ENREGISTREMENT {pages}",
    'status.reading': "LECTURE DU TEXTE {pages}",
    'status.cancelling': "ARRÊT",
    'status.saved': "ENREGISTRÉ",
    'status.error': "UN PROBLÈME EST SURVENU",
    'status.no_scanner': "AUCUN NUMÉRISEUR",

    'label.scanner': "Numériseur",
    'label.source': "Source",
    'label.resolution': "Résolution (ppp)",
    'label.colour': "Couleur",
    'label.area': "Zone",
    'label.save_as': "Enregistrer en",
    'label.pages': "Pages",
    'source.glass': "Vitre",
    'source.feeder': "Chargeur",
    'source.duplex': "Recto verso",
    'mode.color': "Couleur",
    'mode.gray': "Gris",
    'mode.bw': "N&B",
    'button.preview': "Aperçu",
    'button.scan': "Numériser",
    'button.scan_feeder': "Tout numériser",
    'button.cancel': "Annuler",
    'button.save': "Enregistrer",
    'button.save_n': "Enregistrer {n} pages",
    'button.whole': "Toute la vitre",
    'button.clear': "Vider",
    'button.open_folder': "Ouvrir le dossier",
    'tip.look_again': "Chercher les numériseurs de nouveau",
    'tip.up': "Monter la page (Alt+Haut)",
    'tip.down': "Descendre la page (Alt+Bas)",
    'tip.delete': "Supprimer la page (Suppr)",
    'tip.rotate_all': "Tourner toutes les pages à droite (Ctrl+Maj+R)",
    'ocr.toggle': "Texte cherchable",
    'ocr.missing': "Les PDF cherchables demandent tesseract, qui n'est pas installé.",
    'ocr.no_lang': "tesseract n'a ni l'anglais ni le français d'installé.",
    'ocr.pdf_only': "Le texte cherchable est pour les PDF.",
    'save.to': "Dans {folder}",

    'scanner.looking': "Recherche des numériseurs. Ceux du réseau peuvent prendre jusqu'à "
                       "30 secondes à répondre.",
    'scanner.none': "Aucun numériseur trouvé. Vérifiez qu'il est allumé, et branché en USB "
                    "ou sur le même réseau que ce PC. Puis appuyez sur la flèche pour "
                    "chercher de nouveau.",
    'scanner.no_sane': "Le programme scanimage de SANE n'est pas installé : Spark Scan ne "
                       "peut joindre aucun numériseur. Sur Fedora : sudo dnf install "
                       "sane-backends",
    'scanner.list_failed': "La recherche des numériseurs a échoué : {detail}",
    'scanner.list_timeout': "Aucune réponse des numériseurs après 40 secondes. Appuyez sur la "
                            "flèche pour chercher de nouveau.",
    'scanner.not_found': "{name} n'a pas répondu. Vérifiez qu'il est allumé, puis appuyez "
                         "sur la flèche pour chercher de nouveau.",
    'scanner.pick': "Choisir un numériseur",
    'scanner.last': "{name} (dernier utilisé)",
    'scanner.network': "réseau",
    'scanner.usb': "USB",

    'view.empty': "Appuyez sur Aperçu pour voir ce qui est sur la vitre,\nou sur Numériser "
                  "pour tout numériser.",
    'view.preview': "APERÇU · GLISSEZ POUR CHOISIR LA PARTIE À NUMÉRISER",
    'view.preview_crop': "APERÇU · SEULE LA PARTIE MARQUÉE SERA NUMÉRISÉE",
    'view.page': "PAGE {n} DE {count} · {dpi} PPP · {w} × {h} MM",
    'view.feeder': "Mettez les pages dans le chargeur, puis appuyez sur Tout numériser.\n"
                   "L'aperçu fonctionne sur la vitre seulement.",
    'area.whole': "Toute la vitre",
    'area.part': "{w} × {h} mm",
    'area.feeder': "Page entière (chargeur)",

    'tip.rotate_left': "Tourner à gauche (Ctrl+L)",
    'tip.rotate_right': "Tourner à droite (Ctrl+R)",
    'tip.rotate_180': "Tourner de 180°",
    'edit.straighten': "Redresser",
    'edit.whiten': "Blanchir le fond",
    'edit.brightness': "Luminosité",
    'edit.contrast': "Contraste",
    'edit.reset': "Rétablir",
    'edit.measuring': "Mesure de l'angle…",
    'edit.straightened': "Redressée de {angle}°.",
    'edit.straight': "Déjà droite.",
    'edit.no_lines': "Aucune ligne de texte pour la redresser; la page reste telle quelle.",
    'edit.bw': "Les pages en noir et blanc n'ont ni luminosité ni contraste.",
    'edit.new_pages': "Redresser et Blanchir le fond restent actifs pour les pages suivantes.",
    'done.turned_all': "Pages tournées : {pages}.",

    'pages.count': "{n} pages",
    'pages.one': "1 page",
    'pages.none': "Aucune page.",

    'done.page': "Page {n} numérisée.",
    'done.pages': "{n} pages numérisées.",
    'done.feeder_partial': "Arrêté après {n} pages.",
    'done.saved': "Enregistré : {name}",
    'done.saved_n': "{n} fichiers enregistrés : {name} …",
    'done.cancelled': "Annulé.",
    'error.no_docs': "Le chargeur est vide. Mettez-y les pages, dans le sens montré sur "
                     "l'imprimante, et numérisez de nouveau.",
    'error.jammed': "Le papier est coincé. Dégagez-le sur l'imprimante, puis numérisez de "
                    "nouveau.",
    'error.cover_open': "Le couvercle du numériseur est ouvert. Fermez-le et numérisez de "
                        "nouveau.",
    'error.busy': "Le numériseur est occupé, peut-être à imprimer ou à numériser pour un "
                  "autre programme. Attendez, puis numérisez de nouveau.",
    'error.denied': "Cet utilisateur n'a pas le droit d'utiliser le numériseur.",
    'error.open_failed': "Impossible de joindre le numériseur. Vérifiez qu'il est allumé, et "
                         "toujours sur le réseau ou branché.",
    'error.io': "Le numériseur a cessé de répondre pendant la numérisation. Vérifiez sa "
                "connexion et numérisez de nouveau.",
    'error.no_mem': "Le numériseur manque de mémoire. Essayez une résolution plus basse.",
    'error.options_timeout': "Le numériseur n'a pas répondu. Vérifiez qu'il est allumé, puis "
                             "appuyez sur la flèche pour chercher de nouveau.",
    'error.list_failed': "La recherche des numériseurs a échoué.",
    'error.no_scanimage': "Le programme scanimage de SANE n'est pas installé.",
    'error.failed': "La numérisation a échoué.",
    'error.save': "Impossible d'enregistrer : {detail}",
    'error.unexpected': "Erreur inattendue : {detail}",
    'error.detail': "Le numériseur a dit : {detail}",

    'close.title': "Fermer Spark Scan?",
    'close.unsaved': "Pages non enregistrées : {pages}. Fermer et les perdre?",
    'clear.title': "Vider les pages?",
    'clear.confirm': "Retirer {pages} de ce document? Les fichiers enregistrés ne sont pas "
                     "touchés.",

    'file.scan': "Numérisation",
    'file.page': "page",
}

TABLES = {'en': EN, 'fr': FR}


def language() -> str:
    """'fr' or 'en'. SPARK_LANG=en|fr wins; otherwise the first of LC_ALL, LC_MESSAGES and
    LANG that is set, French if it starts with fr (fr_CA.UTF-8, fr_FR, fr)."""
    forced = os.environ.get('SPARK_LANG', '').strip().lower()
    if forced in TABLES:
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


_T = TABLES[language()]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text


def pages_word(n: int) -> str:
    return t('pages.one') if n == 1 else t('pages.count', n=n)


def decimal(value: float, places: int = 1) -> str:
    """3.2 in English, 3,2 in French."""
    text = f"{value:.{places}f}"
    return text.replace('.', ',') if _T is FR else text
