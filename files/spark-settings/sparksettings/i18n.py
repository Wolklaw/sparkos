"""Every word on screen goes through _(): the English text is the key, the French is in fr.py.
A string with no French entry shows in English, and the tests fail on it."""

from .lang import ui_language

_fr = None


def _(text: str) -> str:
    global _fr
    if ui_language() != 'fr':
        return text
    if _fr is None:
        from .fr import FR
        _fr = FR
    return _fr.get(text, text)


def both(text: str) -> str:
    """English and French together, lower-cased, for searching in either language."""
    from .fr import FR
    return f"{text} {FR.get(text, '')}".lower()
