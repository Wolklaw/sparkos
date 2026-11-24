"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    'search.placeholder': "Search emoji and symbols",
    'search.none': "Nothing matches “{query}”.",
    'group.recent': "Recently used",
    'recent.empty': "Nothing yet. What you pick shows up here.",
    'tip.tone': "Skin tone",
    'tone.default': "Default",
    'tone.0': "Light",
    'tone.1': "Medium-light",
    'tone.2': "Medium",
    'tone.3': "Medium-dark",
    'tone.4': "Dark",
    'hint.idle': "Enter picks the first result. Right-click for skin tones.",
    'status.pasted': "Pasted {char}",
    'status.copied': "Copied {char}. Press Ctrl+V to paste it.",
    'status.copied_failed': "Copied {char}. Pasting didn't work: {why}. Press Ctrl+V.",
    'paste.enable': "Turn on pasting",
    'paste.enable_tip': "Copying works already. To paste into the window you were in, the "
                        "desktop asks once whether Spark Emoji may press Ctrl+V.",
    'paste.waiting': "Waiting for your answer on the desktop…",
    'paste.on': "Pasting is on.",
    'paste.refused': "Pasting stays off: {why}.",
    'notify.title': "Copied {char}",
    'notify.body': "Press Ctrl+V to paste it.",
    'about.emoji': "Emoji",
    'about.symbols': "Symbols",
    'kind.symbol': "Symbol",
}

FR = {
    'search.placeholder': "Chercher un émoji ou un symbole",
    'search.none': "Rien ne correspond à « {query} ».",
    'group.recent': "Récemment utilisés",
    'recent.empty': "Rien pour l'instant. Ce que vous choisissez apparaît ici.",
    'tip.tone': "Teinte de peau",
    'tone.default': "Par défaut",
    'tone.0': "Claire",
    'tone.1': "Moyennement claire",
    'tone.2': "Moyenne",
    'tone.3': "Moyennement foncée",
    'tone.4': "Foncée",
    'hint.idle': "Entrée choisit le premier résultat. Clic droit pour les teintes de peau.",
    'status.pasted': "{char} collé",
    'status.copied': "{char} copié. Faites Ctrl+V pour le coller.",
    'status.copied_failed': "{char} copié. Le collage n'a pas marché : {why}. Faites Ctrl+V.",
    'paste.enable': "Activer le collage",
    'paste.enable_tip': "La copie marche déjà. Pour coller dans la fenêtre où vous étiez, "
                        "le bureau demande une fois si Spark Emoji peut appuyer sur Ctrl+V.",
    'paste.waiting': "En attente de votre réponse sur le bureau…",
    'paste.on': "Le collage est activé.",
    'paste.refused': "Le collage reste désactivé : {why}.",
    'notify.title': "{char} copié",
    'notify.body': "Faites Ctrl+V pour le coller.",
    'about.emoji': "Émojis",
    'about.symbols': "Symboles",
    'kind.symbol': "Symbole",
}


def t(key: str, **values) -> str:
    table = FR if ui_language() == 'fr' else EN
    text = table.get(key) or EN[key]
    return text.format(**values) if values else text
