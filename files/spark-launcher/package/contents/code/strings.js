.pragma library
// Every word Spark Launcher shows, in one place. English and French (Quebec).

const STRINGS = {
    en: {
        search: "Search apps, settings and files",
        pinned: "PINNED",
        allApps: "ALL APPS",
        recent: "RECENT FILES",
        noRecent: "Files you open show up here.",
        apps: "APPS",
        other: "SETTINGS, FILES AND MORE",
        nothing: "Nothing found for \"%1\".",
        sumHint: "Enter copies the answer",
        copied: "Copied",
        findMore: "FIND MORE APPS",
        findMoreTip: "Opens Spark Store",
        lock: "LOCK",
        sleep: "SLEEP",
        signOut: "SIGN OUT",
        restart: "RESTART",
        shutDown: "SHUT DOWN",
        confirmRestart: "Restart now? Unsaved work in open apps is lost.",
        confirmShutDown: "Shut down now? Unsaved work in open apps is lost.",
        confirmSignOut: "Sign out now? Unsaved work in open apps is lost.",
        cancel: "CANCEL",
        pin: "PIN TO LAUNCHER",
        unpin: "UNPIN",
        noPinned: "Right-click an app below and pick Pin to launcher.",
        empty: "No apps found.",
    },
    fr: {
        search: "Chercher des applis, des réglages et des fichiers",
        pinned: "ÉPINGLÉES",
        allApps: "TOUTES LES APPLIS",
        recent: "FICHIERS RÉCENTS",
        noRecent: "Les fichiers que vous ouvrez apparaissent ici.",
        apps: "APPLIS",
        other: "RÉGLAGES, FICHIERS ET PLUS",
        nothing: "Rien trouvé pour « %1 ».",
        sumHint: "Entrée copie la réponse",
        copied: "Copié",
        findMore: "PLUS D'APPLIS",
        findMoreTip: "Ouvre Spark Store",
        lock: "VERROUILLER",
        sleep: "VEILLE",
        signOut: "DÉCONNEXION",
        restart: "REDÉMARRER",
        shutDown: "ÉTEINDRE",
        confirmRestart: "Redémarrer maintenant? Le travail non enregistré dans les applis ouvertes sera perdu.",
        confirmShutDown: "Éteindre maintenant? Le travail non enregistré dans les applis ouvertes sera perdu.",
        confirmSignOut: "Se déconnecter maintenant? Le travail non enregistré dans les applis ouvertes sera perdu.",
        cancel: "ANNULER",
        pin: "ÉPINGLER AU LANCEUR",
        unpin: "DÉSÉPINGLER",
        noPinned: "Faites un clic droit sur une appli plus bas et choisissez Épingler au lanceur.",
        empty: "Aucune appli trouvée.",
    },
};

// "fr_CA" -> "fr"; anything without a table falls back to English.
function language(localeName) {
    const lang = String(localeName || "").split(/[_\-.]/)[0].toLowerCase();
    return STRINGS[lang] ? lang : "en";
}

function tr(lang, key, arg) {
    const table = STRINGS[lang] || STRINGS.en;
    let text = table[key] !== undefined ? table[key] : STRINGS.en[key];
    if (text === undefined) {
        return key;
    }
    if (arg !== undefined) {
        text = text.replace("%1", arg);
    }
    return text;
}

function keys(lang) {
    return Object.keys(STRINGS[lang] || {});
}
