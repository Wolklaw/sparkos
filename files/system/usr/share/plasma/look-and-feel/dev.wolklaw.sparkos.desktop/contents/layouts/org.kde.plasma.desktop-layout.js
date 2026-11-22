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
top.addWidget("org.kde.plasma.systemtray");

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
    "org.kde.dolphin.desktop",
    "dev.wolklaw.SparkStore.desktop",
    "dev.wolklaw.SparkGames.desktop",
    "org.kde.konsole.desktop"
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
