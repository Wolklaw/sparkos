"""Every sentence the interface shows, in English and in French (Quebec). The PC's language
picks the table (lang.py); t('key', name=...) fills in the blanks."""

from .lang import ui_language

EN = {
    # tabs
    'tab.outputs': "Outputs",
    'tab.inputs': "Inputs",
    'tab.apps': "Apps",
    'tab.eq': "EQ",
    'tab.scarlett': "Scarlett",

    # status line
    'status.live': "LIVE",
    'status.no_pipewire': "PIPEWIRE NOT RUNNING",
    'status.test_data': "TEST DATA",
    'status.crashed': "SOMETHING WENT WRONG",

    # rows
    'row.mute': "Mute",
    'row.default': "Default",
    'row.set_default': "Set default",
    'row.eq': "EQ",
    'row.with_eq': "{name} (EQ)",
    'empty.outputs': "No output found. Plug in a speaker or headset, or check that PipeWire is running.",
    'empty.inputs': "No input found. Plug in a microphone, or check that PipeWire is running.",

    # sound cards
    'cards.title': "Sound cards",
    'cards.hint': "Some cards have more than one mode: an HDMI card with nothing plugged in has no "
                  "output until a screen with sound is connected, and the onboard card can switch "
                  "between its analog and digital jacks. Pick the mode here.",

    # messages
    'msg.default': "{name} is now the default.",
    'msg.profile': "Changed the mode of {card}.",
    'msg.moved': "{app} now plays on {to}.",
    'msg.eq_on': "EQ is on.",
    'msg.eq_failed': "EQ could not start. See the log.",
    'msg.eq_off': "EQ is off.",
    'msg.eq_removed': "EQ removed for this output.",
    'msg.eq_removed_all': "Every EQ and its service are gone.",

    # mic test
    'mic.title': "Mic test",
    'mic.hint': "Records 3 seconds from the default input, then plays them back on the default output.",
    'mic.start': "Test mic",
    'mic.stop': "Stop",
    'mic.recording': "RECORDING, {secs} S",
    'mic.playing': "PLAYING BACK",
    'mic.failed': "FAILED: {error}",
    'mic.no_input': "No input to test.",

    # apps
    'apps.playing': "Playing",
    'apps.recording': "Recording",
    'apps.none_playing': "No app is playing sound.",
    'apps.none_recording': "No app is recording.",

    # EQ
    'eq.intro': "A five-band equalizer for one output at a time. It adds a virtual output named "
                "after the real one, with (EQ) at the end, and sends the sound through it. Turn it "
                "off or remove it and nothing is left behind.",
    'eq.output': "Output",
    'eq.on': "Equalizer on",
    'eq.preset': "Preset",
    'eq.p.flat': "Flat",
    'eq.p.bass': "Bass boost",
    'eq.p.treble': "Treble boost",
    'eq.p.voice': "Voice",
    'eq.p.warm': "Warm",
    'eq.p.loudness': "Loudness",
    'eq.p.custom': "Custom",
    'eq.band.1': "Bass",
    'eq.band.2': "Low mid",
    'eq.band.3': "Mid",
    'eq.band.4': "Presence",
    'eq.band.5': "Treble",
    'eq.active': "ACTIVE",
    'eq.starting': "STARTING",
    'eq.off': "OFF",
    'eq.remove_one': "Remove EQ from this output",
    'eq.remove_all': "Remove every EQ",
    'eq.footer': "The EQ runs as a user service, spark-audio-eq.service, so it keeps working when "
                 "this window is closed. Removing it stops that service and deletes its files. "
                 "Boosts lower the overall level a little so they don't clip. Double-click a band "
                 "to reset it.",

    # Scarlett
    'scarlett.note': "{name}: the controls come from the kernel's scarlett2 driver. This page has "
                     "not been tried on a real interface yet; if something is missing or does the "
                     "wrong thing, tell the owner.",
    'scarlett.input': "Input {n}",
    'scarlett.phantom': "Phantom power",
    'scarlett.phantom_hint': "48 V. Turn it off before plugging in a ribbon microphone.",
    'scarlett.monitor': "Monitoring",
    'scarlett.outputs': "Outputs",
    'scarlett.mix': "Monitor mix",
    'scarlett.mix_hint': "What goes into each mix",
    'scarlett.mix_n': "Mix {letter}",
    'scarlett.mix_input': "Input {n}",
    'scarlett.routing': "Routing",
    'scarlett.routing_hint': "Where each output gets its sound",
    'scarlett.status': "Status",
    'scarlett.other': "Other controls",
    'scarlett.empty': "This interface shows no controls.",
    'scarlett.write_failed': "Could not change {name}.",
}

FR = {
    'tab.outputs': "Sorties",
    'tab.inputs': "Entrées",
    'tab.apps': "Applis",
    'tab.eq': "Égaliseur",
    'tab.scarlett': "Scarlett",

    'status.live': "EN DIRECT",
    'status.no_pipewire': "PIPEWIRE NE TOURNE PAS",
    'status.test_data': "DONNÉES DE TEST",
    'status.crashed': "QUELQUE CHOSE A MAL TOURNÉ",

    'row.mute': "Muet",
    'row.default': "Par défaut",
    'row.set_default': "Mettre par défaut",
    'row.eq': "Égaliseur",
    'row.with_eq': "{name} (égaliseur)",
    'empty.outputs': "Aucune sortie trouvée. Branchez des haut-parleurs ou un casque, ou vérifiez "
                     "que PipeWire tourne.",
    'empty.inputs': "Aucune entrée trouvée. Branchez un micro, ou vérifiez que PipeWire tourne.",

    'cards.title': "Cartes son",
    'cards.hint': "Certaines cartes ont plus d'un mode : une carte HDMI sans écran branché n'a "
                  "aucune sortie tant qu'un écran avec du son n'est pas connecté, et la carte "
                  "intégrée peut passer de ses prises analogiques à ses prises numériques. "
                  "Choisissez le mode ici.",

    'msg.default': "{name} est maintenant par défaut.",
    'msg.profile': "Mode de {card} changé.",
    'msg.moved': "{app} joue maintenant sur {to}.",
    'msg.eq_on': "L'égaliseur est activé.",
    'msg.eq_failed': "L'égaliseur n'a pas pu démarrer. Voyez le journal.",
    'msg.eq_off': "L'égaliseur est désactivé.",
    'msg.eq_removed': "Égaliseur retiré pour cette sortie.",
    'msg.eq_removed_all': "Tous les égaliseurs et leur service sont retirés.",

    'mic.title': "Test du micro",
    'mic.hint': "Enregistre 3 secondes de l'entrée par défaut, puis les rejoue sur la sortie par défaut.",
    'mic.start': "Tester le micro",
    'mic.stop': "Arrêter",
    'mic.recording': "ENREGISTREMENT, {secs} S",
    'mic.playing': "LECTURE",
    'mic.failed': "ÉCHEC : {error}",
    'mic.no_input': "Aucune entrée à tester.",

    'apps.playing': "En lecture",
    'apps.recording': "En enregistrement",
    'apps.none_playing': "Aucune appli ne joue de son.",
    'apps.none_recording': "Aucune appli n'enregistre.",

    'eq.intro': "Un égaliseur à cinq bandes, pour une sortie à la fois. Il ajoute une sortie virtuelle "
                "qui porte le nom de la vraie, suivi de (égaliseur), et y fait passer le son. "
                "Désactivez-le ou retirez-le et il ne reste rien.",
    'eq.output': "Sortie",
    'eq.on': "Égaliseur activé",
    'eq.preset': "Préréglage",
    'eq.p.flat': "Neutre",
    'eq.p.bass': "Graves accentués",
    'eq.p.treble': "Aigus accentués",
    'eq.p.voice': "Voix",
    'eq.p.warm': "Chaud",
    'eq.p.loudness': "Loudness",
    'eq.p.custom': "Personnalisé",
    'eq.band.1': "Graves",
    'eq.band.2': "Bas-médium",
    'eq.band.3': "Médium",
    'eq.band.4': "Présence",
    'eq.band.5': "Aigus",
    'eq.active': "ACTIF",
    'eq.starting': "DÉMARRAGE",
    'eq.off': "INACTIF",
    'eq.remove_one': "Retirer l'égaliseur de cette sortie",
    'eq.remove_all': "Retirer tous les égaliseurs",
    'eq.footer': "L'égaliseur tourne comme un service utilisateur, spark-audio-eq.service, et "
                 "continue de fonctionner quand cette fenêtre est fermée. Le retirer arrête ce "
                 "service et supprime ses fichiers. Les accentuations baissent un peu le niveau "
                 "général pour éviter la saturation. Double-cliquez sur une bande pour la remettre "
                 "à zéro.",

    'scarlett.note': "{name} : les commandes viennent du pilote scarlett2 du noyau. Cette page n'a "
                     "pas encore été essayée sur une vraie interface; si quelque chose manque ou "
                     "fait autre chose que prévu, dites-le au propriétaire.",
    'scarlett.input': "Entrée {n}",
    'scarlett.phantom': "Alimentation fantôme",
    'scarlett.phantom_hint': "48 V. Coupez-la avant de brancher un micro à ruban.",
    'scarlett.monitor': "Écoute de contrôle",
    'scarlett.outputs': "Sorties",
    'scarlett.mix': "Mixage d'écoute",
    'scarlett.mix_hint': "Ce qui entre dans chaque mixage",
    'scarlett.mix_n': "Mixage {letter}",
    'scarlett.mix_input': "Entrée {n}",
    'scarlett.routing': "Routage",
    'scarlett.routing_hint': "D'où chaque sortie tire son son",
    'scarlett.status': "État",
    'scarlett.other': "Autres commandes",
    'scarlett.empty': "Cette interface n'affiche aucune commande.",
    'scarlett.write_failed': "Impossible de modifier {name}.",
}

TABLES = {'en': EN, 'fr': FR}
LANG = ui_language()
_T = TABLES[LANG]


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
