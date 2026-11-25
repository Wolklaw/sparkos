"""Every word the polkit window and the greeter show, in English and French. t(key, **values)
picks the PC's language (lang.ui_language)."""

from .lang import ui_language

TEXT = {
    # polkit window
    'auth.title': ('AUTHENTICATION REQUIRED', 'AUTHENTIFICATION REQUISE'),
    'auth.asking': ('{who} wants to do this', '{who} veut faire ceci'),
    'auth.program': ('PROGRAM', 'PROGRAMME'),
    'auth.command': ('COMMAND', 'COMMANDE'),
    'auth.action': ('ACTION', 'ACTION'),
    'auth.as': ('AUTHENTICATE AS', "S'AUTHENTIFIER EN TANT QUE"),
    'auth.password': ('Password', 'Mot de passe'),
    'auth.unknown_program': ('an unknown program', 'un programme inconnu'),
    'auth.ok': ('AUTHENTICATE', "S'AUTHENTIFIER"),
    'auth.cancel': ('CANCEL', 'ANNULER'),
    'auth.wrong': ('That password did not work. Try again.',
                   "Ce mot de passe n'a pas fonctionné. Réessayez."),
    'auth.checking': ('Checking...', 'Vérification...'),
    'auth.no_message': ('This program needs your permission.',
                        'Ce programme a besoin de votre permission.'),
    'auth.you': ('{name} (you)', '{name} (vous)'),
    # greeter
    'greet.title': ('SIGN IN', 'OUVERTURE DE SESSION'),
    'greet.user': ('USER', 'UTILISATEUR'),
    'greet.session': ('SESSION', 'SESSION'),
    'greet.password': ('Password', 'Mot de passe'),
    'greet.sign_in': ('SIGN IN', 'SE CONNECTER'),
    'greet.back': ('BACK', 'RETOUR'),
    'greet.wrong': ('That did not work. Try again.', "Ça n'a pas fonctionné. Réessayez."),
    'greet.failed': ('Could not start the session: {why}',
                     'Impossible de démarrer la session : {why}'),
    'greet.no_users': ('No users on this PC.', 'Aucun utilisateur sur ce PC.'),
    'greet.suspend': ('SLEEP', 'VEILLE'),
    'greet.reboot': ('RESTART', 'REDÉMARRER'),
    'greet.poweroff': ('SHUT DOWN', 'ÉTEINDRE'),
    'greet.no_daemon': ('The sign-in service is not answering.',
                        "Le service d'ouverture de session ne répond pas."),
    'greet.waiting': ('Checking...', 'Vérification...'),
    'greet.other': ('Other user...', 'Autre utilisateur...'),
    'greet.name': ('User name', "Nom d'utilisateur"),
    'greet.power_failed': ('{what} did not work.', "{what} n'a pas fonctionné."),
}


def t(key: str, language=None, **values) -> str:
    en, fr = TEXT[key]
    text = fr if (language or ui_language()) == 'fr' else en
    return text.format(**values) if values else text
