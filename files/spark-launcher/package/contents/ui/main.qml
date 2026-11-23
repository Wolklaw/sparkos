// Spark Launcher: SparkOS's app menu. The button on the dock (and the top bar), opened by
// a click or the Meta key. The open launcher is Launcher.qml; this file connects it to
// Plasma: the app, search, favourite and recent-file models (Plasma's own, the ones Kickoff
// uses, so apps and settings are found the same way), session actions, and Spark Calc.
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.plasma.private.kicker as Kicker
import org.kde.plasma.private.sessions as Sessions
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme
import "../code/search.js" as Search

PlasmoidItem {
    id: spark

    // ── Plasma's models ───────────────────────────────────────
    readonly property Kicker.RootModel rootModel: Kicker.RootModel {
        autoPopulate: false
        appletInterface: spark
        flat: true                  // categories, no sub-categories
        sorted: true
        showSeparators: false
        showTopLevelItems: true
        showAllApps: true           // row 0: every app, A to Z
        showAllAppsCategorized: false
        showRecentApps: false
        showRecentDocs: false
        showPowerSession: false
        showFavoritesPlaceholder: false
        highlightNewlyInstalledApps: false

        Component.onCompleted: {
            const favorites = favoritesModel as Kicker.KAStatsFavoritesModel;
            // Pins live in Plasma's activity database under one shared agent: the client id only
            // keeps the order, so Spark Launcher sees whatever Kickoff had pinned. The SparkOS
            // defaults are added only when that list is empty (a new account). Adding a pin that's
            // there already does nothing, so two launchers doing it at first login is harmless.
            favorites.initForClient("dev.wolklaw.sparklauncher.favorites");
            if (!Plasmoid.configuration.favoritesPinned) {
                if (favorites.count < 1) {
                    favorites.portOldFavorites(Plasmoid.configuration.favorites);
                }
                Plasmoid.configuration.favoritesPinned = true;
            }
        }
    }

    // The flat list of every app: row 0 of the root model
    property Kicker.AppsModel allApps: null
    function refreshAllApps() {
        allApps = rootModel.count > 0 ? rootModel.modelForRow(0) : null;
    }
    Connections {
        target: spark.rootModel
        function onRefreshed() { spark.refreshAllApps(); }
        function onCountChanged() { spark.refreshAllApps(); }
    }

    readonly property Kicker.KAStatsFavoritesModel favorites: rootModel.favoritesModel as Kicker.KAStatsFavoritesModel

    readonly property Kicker.RunnerModel runnerModel: Kicker.RunnerModel {
        appletInterface: spark
        mergeResults: true
        favoritesModel: spark.rootModel.favoritesModel
        // Apps, settings pages, recent files, file search (Baloo), places, and the session
        // and power words. Not: the calculator (Spark Calc does sums), stores, web shortcuts.
        runners: ["krunner_services", "krunner_systemsettings", "krunner_recentdocuments",
                  "baloosearch", "krunner_placesrunner", "krunner_sessions", "krunner_powerdevil"]
    }

    readonly property Kicker.RecentUsageModel recentModel: Kicker.RecentUsageModel {
        favoritesModel: spark.rootModel.favoritesModel
        shownItems: Kicker.RecentUsageModel.OnlyDocs
    }

    Sessions.SessionManagement { id: session }

    // Spark Calc answers sums: `spark-calc --eval` (about 50 ms, nothing runs while idle)
    P5Support.DataSource {
        id: calc
        engine: "executable"
        connectedSources: []
        property string asked: ""
        property string sum: ""
        onNewData: (source, data) => {
            disconnectSource(source);
            if (source !== asked) {
                return;                       // an older sum; the person kept typing
            }
            const ok = data["exit code"] === 0;
            spark.sumAsked = sum;
            spark.sumAnswer = ok ? String(data.stdout).trim() : "";
        }
        function ask(s) {
            const cmd = Search.sumCommand(s);
            if (cmd === "") {
                return;
            }
            sum = s;
            asked = cmd;
            connectSource(cmd);
        }
    }
    property string sumAnswer: ""
    property string sumAsked: ""

    // ── Plasma applet settings ───────────────────────────────
    Plasmoid.icon: Plasmoid.configuration.icon
    preferredRepresentation: compactRepresentation
    switchWidth: Kirigami.Units.gridUnit * 30
    switchHeight: Kirigami.Units.gridUnit * 25
    toolTipMainText: "Spark Launcher"
    toolTipSubText: ""

    // Plasma's models fill once, the first time the launcher opens (like Kickoff); after
    // that they follow installs and removals on their own, so opening again costs nothing.
    property bool populated: false
    onExpandedChanged: {
        if (spark.expanded) {
            if (!populated) {
                rootModel.refresh();
                populated = true;
            }
            refreshAllApps();
            if (fullRepresentationItem) {
                (fullRepresentationItem as Launcher).opened();
            }
        } else {
            runnerModel.query = "";
        }
    }

    // ── The button ─────────────────────────────────────────────
    compactRepresentation: MouseArea {
        id: button
        readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
        readonly property bool showLabel: !vertical && Plasmoid.configuration.menuLabel !== ""
        readonly property bool lit: containsMouse || spark.expanded
        // The panel's thickness, at most Plasma's "huge" icon size
        readonly property real iconSize: Math.min(vertical ? width : height, Kirigami.Units.iconSizes.huge)
        property bool wasExpanded

        Layout.preferredWidth: vertical ? -1 : row.implicitWidth + (showLabel ? Kirigami.Units.smallSpacing * 2 : 0)
        Layout.preferredHeight: vertical ? iconSize : -1
        Layout.minimumWidth: vertical ? -1 : Layout.preferredWidth
        hoverEnabled: true
        Accessible.name: "Spark Launcher"
        Accessible.role: Accessible.Button

        onPressed: wasExpanded = spark.expanded
        onClicked: spark.expanded = !wasExpanded

        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Icon {
                Layout.preferredWidth: button.iconSize
                Layout.preferredHeight: button.iconSize
                source: Plasmoid.icon
                active: button.lit
            }
            // The SPARKOS wordmark in the top bar, in the splash screen's type
            SlipText {
                visible: button.showLabel
                text: Plasmoid.configuration.menuLabel
                color: button.lit ? Theme.accent : Theme.text
                rest: 1
                font.family: "Chakra Petch"
                font.pixelSize: Math.max(10, Math.round(button.height * 0.45))
                font.letterSpacing: 3
            }
        }
    }

    // ── The open launcher ─────────────────────────────────────
    fullRepresentation: Launcher {
        id: launcher
        focus: true
        motion: Kirigami.Units.longDuration > 0
        favoritesModel: spark.rootModel.favoritesModel
        categoriesModel: spark.rootModel
        categoryModelFor: row => spark.rootModel.modelForRow(row)
        allAppsModel: spark.allApps
        runnerModel: spark.runnerModel.count ? spark.runnerModel.modelForRow(0) : null
        runnerBusy: spark.runnerModel.querying
        recentModel: spark.recentModel
        isPinned: id => spark.favorites.isFavorite(id)
        sumAnswer: spark.sumAnswer
        sumAsked: spark.sumAsked
        canSuspend: session.canSuspend

        onQueryChanged: spark.runnerModel.query = query
        onActivate: (model, row) => {
            spark.expanded = false;
            if (model) {
                model.trigger(row, "", null);
            }
        }
        onPinRequested: id => spark.favorites.addFavorite(id)
        onUnpinRequested: id => spark.favorites.removeFavorite(id)
        onSumRequested: sum => calc.ask(sum)
        onCloseRequested: spark.expanded = false
        onPowerRequested: what => {
            spark.expanded = false;
            if (what === "lock") {
                session.lock();
            } else if (what === "sleep") {
                session.suspend();
            } else if (what === "logout") {
                session.requestLogout(Sessions.SessionManagement.ConfirmationMode.Skip);
            } else if (what === "restart") {
                session.requestReboot(Sessions.SessionManagement.ConfirmationMode.Skip);
            } else if (what === "shutdown") {
                session.requestShutdown(Sessions.SessionManagement.ConfirmationMode.Skip);
            }
        }
    }

    Component.onCompleted: {
        Plasmoid.activationTogglesExpanded = true;
        refreshAllApps();
    }
}
