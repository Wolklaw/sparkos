/*
    SparkOS: Spark Notes replaces Klipper (the "Clipboard" entry of the system tray). Klipper runs
    inside plasmashell for as long as that entry is on, and keeps Meta+V. This takes it out of the
    tray of a profile that already exists (the default layout does the same for a new one) and
    drops Klipper's old Meta+V entry so Spark Notes can have the key.

    Plasma runs each update script once per profile. The clipboard entry stays in knownItems, so
    the tray does not add it back as a "new" item; a person can still turn it on in the tray's
    settings (Entries), but then it takes Meta+V back.
*/

function without(list, item) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
        if (list[i] !== item && list[i] !== "") {
            out.push(list[i]);
        }
    }
    return out;
}

function inList(list, item) {
    for (var i = 0; i < list.length; i++) {
        if (list[i] === item) {
            return true;
        }
    }
    return false;
}

function dropClipboard(tray) {
    // the entry itself
    var widgets = tray.widgets();
    for (var i = 0; i < widgets.length; i++) {
        if (widgets[i].type === "org.kde.plasma.clipboard") {
            widgets[i].remove();
        }
    }
    // the list of entries that are on, and the list the tray has already seen
    tray.currentConfigGroup = ["General"];
    var extra = tray.readConfig("extraItems");
    if (extra) {
        tray.writeConfig("extraItems", without(String(extra).split(","), "org.kde.plasma.clipboard").join(","));
    }
    var known = String(tray.readConfig("knownItems") || "").split(",");
    if (!inList(known, "org.kde.plasma.clipboard")) {
        known.push("org.kde.plasma.clipboard");
        tray.writeConfig("knownItems", without(known, "").join(","));
    }
}

var containments = desktops().concat(panels());
for (var c = 0; c < containments.length; c++) {
    var widgets = containments[c].widgets();
    for (var w = 0; w < widgets.length; w++) {
        if (widgets[w].type === "org.kde.plasma.systemtray") {
            var trayId = widgets[w].readConfig("SystrayContainmentId");
            if (trayId) {
                try {
                    dropClipboard(desktopById(trayId));
                } catch (e) {
                    print("sparkos-no-klipper: could not change the tray: " + e);
                }
            }
        }
    }
}

// Klipper's old Meta+V (it lives in plasmashell's shortcut group)
try {
    var shortcuts = ConfigFile("kglobalshortcutsrc", "plasmashell");
    shortcuts.deleteEntry("show-on-mouse-pos");
} catch (e) {
    print("sparkos-no-klipper: could not clear the old Meta+V: " + e);
}
