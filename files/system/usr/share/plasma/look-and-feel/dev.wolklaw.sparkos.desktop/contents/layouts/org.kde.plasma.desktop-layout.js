// SparkOS default desktop: a slim top bar (SparkOS menu, tray, clock) and a floating,
// centred dock with the launcher and pinned apps. Both menus are Spark Launcher
// (files/spark-launcher), SparkOS's own app menu, in place of Plasma's Kickoff. Used only
// for a user's first login; after that the user's own panel setup is kept.

var wallpaper = "/usr/share/wallpapers/SparkOS";
var desktops = desktopsForActivity(currentActivity());
for (var i = 0; i < desktops.length; i++) {
    desktops[i].wallpaperPlugin = "org.kde.image";
    desktops[i].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktops[i].writeConfig("Image", wallpaper);
}

// Top bar
var top = new Panel;
top.location = "top";
top.height = Math.round(gridUnit * 1.8);
top.floating = false;
top.hiding = "none";

var menu = top.addWidget("dev.wolklaw.sparklauncher");
menu.currentConfigGroup = ["General"];
menu.writeConfig("icon", "sparkos");
menu.writeConfig("menuLabel", "SPARKOS");

top.addWidget("org.kde.plasma.panelspacer");
var tray = top.addWidget("org.kde.plasma.systemtray");

// No Clipboard entry in the tray: it is Klipper, and Spark Notes (files/spark-notes) replaces it
// and has Meta+V. The lists are Plasma 6's own default entries (copied from a fresh profile)
// without org.kde.plasma.clipboard; it stays in knownItems so the tray doesn't add it back as
// new. If this fails the tray keeps its defaults, Klipper stays on, and Spark Notes still works
// (Meta+V stays with Klipper until the entry is turned off in the tray's settings).
try {
    var trayId = tray.readConfig("SystrayContainmentId");
    if (trayId) {
        var others = ["org.kde.kdeconnect", "org.kde.plasma.vault", "org.kde.kscreen",
                      "org.kde.plasma.battery", "org.kde.plasma.bluetooth",
                      "org.kde.plasma.brightness", "org.kde.plasma.cameraindicator",
                      "org.kde.plasma.devicenotifier", "org.kde.plasma.dwellclicker",
                      "org.kde.plasma.keyboardindicator", "org.kde.plasma.keyboardlayout",
                      "org.kde.plasma.manage-inputmethod", "org.kde.plasma.mediacontroller",
                      "org.kde.plasma.networkmanagement", "org.kde.plasma.notifications",
                      "org.kde.plasma.printmanager", "org.kde.plasma.volume",
                      "org.kde.plasma.weather"];
        var trayContainment = desktopById(trayId);
        trayContainment.currentConfigGroup = ["General"];
        trayContainment.writeConfig("extraItems", others.join(","));
        trayContainment.writeConfig("knownItems",
                                    others.concat(["org.kde.plasma.clipboard"]).join(","));
    }
} catch (e) {
    print("sparkos layout: could not turn Clipboard off in the tray: " + e);
}

var clock = top.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateDisplayFormat", "BesideTime");
clock.writeConfig("dateFormat", "custom");
clock.writeConfig("customDateFormat", "ddd d MMM");

// Dock
var dock = new Panel;
dock.location = "bottom";
dock.height = Math.round(gridUnit * 3.4);
dock.floating = true;
dock.lengthMode = "fit";
dock.alignment = "center";
dock.hiding = "none";

var launcher = dock.addWidget("dev.wolklaw.sparklauncher");
launcher.currentConfigGroup = ["General"];
launcher.writeConfig("icon", "sparkos");

dock.addWidget("org.kde.plasma.marginsseparator");

// Pinned apps. Only ones that are installed are added, so a missing app never shows a broken icon.
var pinned = [
    "dev.wolklaw.Soot.desktop",
    "freesuite.desktop",
    "dev.wolklaw.SparkFiles.desktop",
    "dev.wolklaw.SparkStore.desktop",
    "dev.wolklaw.SparkGames.desktop",
    "dev.wolklaw.SparkTerminal.desktop",
    "dev.wolklaw.SparkSettings.desktop"
];
var launchers = [];
for (var j = 0; j < pinned.length; j++) {
    if (applicationExists(pinned[j])) {
        launchers.push("applications:" + pinned[j]);
    }
}
var tasks = dock.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", launchers.join(","));
