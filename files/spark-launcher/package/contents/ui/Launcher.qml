// The open launcher: search box, pinned apps, all apps by category, recent files and the
// power buttons. It knows nothing about Plasma: main.qml hands it Plasma's models and acts on
// its signals, so the tests can hand it plain ListModels instead.
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme
import "../code/strings.js" as Strings
import "../code/search.js" as Search

FocusScope {
    id: root

    // ── In (from main.qml, or from a test) ──────────────────────
    property string lang: Strings.language(Qt.locale().name)
    property bool motion: true
    property var favoritesModel: null      // pinned apps: display, decoration, favoriteId
    property var categoriesModel: null     // categories: display (row 0 is all apps)
    property var categoryModelFor: row => null
    property var allAppsModel: null        // every app, flat: display, decoration, description, favoriteId
    property var runnerModel: null         // KRunner's results for `query`
    property bool runnerBusy: false
    property var recentModel: null         // recent files: display, decoration, description
    property var isPinned: id => false
    property string sumAnswer: ""          // Spark Calc's answer for sumAsked
    property string sumAsked: ""
    property bool canSuspend: true
    property string storeId: "dev.wolklaw.SparkStore.desktop"

    // ── Out ───────────────────────────────────────────────────
    signal activate(var model, int row)    // open row `row` of `model` (main.qml triggers it)
    signal pinRequested(string favoriteId)
    signal unpinRequested(string favoriteId)
    signal sumRequested(string sum)
    signal powerRequested(string what)     // lock, sleep, logout, restart, shutdown
    signal closeRequested()

    // ── State ─────────────────────────────────────────────────
    readonly property alias query: searchField.text
    readonly property bool searching: query.trim() !== ""
    readonly property bool frenchComma: lang === "fr"
    readonly property string sum: Search.sumFrom(query, frenchComma)
    property int category: 0
    property string confirming: ""          // restart, shutdown or logout while asking
    property var results: []
    property var apps: []
    property bool copied: false

    function t(key, arg) { return Strings.tr(lang, key, arg); }

    implicitWidth: 760
    implicitHeight: 600
    Layout.minimumWidth: 640
    Layout.minimumHeight: 520
    Layout.preferredWidth: implicitWidth
    Layout.preferredHeight: implicitHeight

    // Called by main.qml each time the launcher opens
    function opened() {
        searchField.text = "";
        confirming = "";
        copied = false;
        category = 0;
        searchField.forceActiveFocus();
        openTear.restart();
        idleTear.restart();
    }

    // The fault: the wordmark tears and the panel's frame slips for a moment
    function tear() {
        if (!motion) {
            return;
        }
        wordmark.tear();
        frameSlip.restart();
    }

    Timer { id: openTear; interval: 450; onTriggered: root.tear() }
    Timer {
        id: idleTear
        interval: 7000 + Math.random() * 5000
        repeat: true
        running: root.visible && root.motion
        onTriggered: { interval = 7000 + Math.random() * 5000; root.tear(); }
    }

    // ── Apps, read once from the model so the search box can rank them at once ──
    Instantiator {
        id: appIndex
        model: root.allAppsModel
        delegate: AppEntry {}
        onObjectAdded: Qt.callLater(root.collectApps)
        onObjectRemoved: Qt.callLater(root.collectApps)
    }
    function collectApps() {
        const list = [];
        for (let i = 0; i < appIndex.count; i++) {
            const a = appIndex.objectAt(i) as AppEntry;
            if (a && !a.separator && a.name !== "") {
                list.push(a);
            }
        }
        apps = list;
        rebuild();
    }

    function appById(id) {
        const want = String(id).replace(/^applications:/, "");
        for (let i = 0; i < apps.length; i++) {
            if (apps[i].id.replace(/^applications:/, "") === want) {
                return apps[i];
            }
        }
        return null;
    }
    readonly property var store: apps.length >= 0 ? appById(storeId) : null

    Instantiator {
        id: runnerIndex
        model: root.runnerModel
        delegate: AppEntry {}
        onObjectAdded: Qt.callLater(root.rebuild)
        onObjectRemoved: Qt.callLater(root.rebuild)
    }

    // The search results: the sum, then apps (ranked here, instantly), then what KRunner found
    // (settings pages, files, places), without the apps it found again.
    function rebuild() {
        if (!searching) {
            results = [];
            return;
        }
        const out = [];
        if (sum !== "" && sumAnswer !== "" && sumAsked === sum) {
            out.push({ kind: "sum", name: "= " + Search.showAnswer(sumAnswer, frenchComma),
                       description: sum, icon: "accessories-calculator" });
        }
        const found = Search.filterApps(apps, query, 8);
        const names = {};
        if (found.length) {
            out.push({ kind: "heading", name: t("apps") });
            found.forEach(a => {
                names[Search.fold(a.name)] = true;
                out.push({ kind: "app", name: a.name, description: a.description, icon: a.icon, row: a.row, id: a.id });
            });
        }
        const others = [];
        for (let i = 0; i < runnerIndex.count && others.length < 12; i++) {
            const r = runnerIndex.objectAt(i) as AppEntry;
            if (!r || r.name === "" || names[Search.fold(r.name)]) {
                continue;
            }
            others.push({ kind: "runner", name: r.name, description: r.description || r.group, icon: r.icon, row: r.row });
        }
        if (others.length) {
            out.push({ kind: "heading", name: t("other") });
            others.forEach(o => out.push(o));
        }
        results = out;
        resultList.currentIndex = firstSelectable();
    }

    function firstSelectable() {
        for (let i = 0; i < results.length; i++) {
            if (results[i].kind !== "heading") {
                return i;
            }
        }
        return -1;
    }

    function step(by) {
        let i = resultList.currentIndex;
        for (let n = 0; n < results.length; n++) {
            i += by;
            if (i < 0 || i >= results.length) {
                return;
            }
            if (results[i].kind !== "heading") {
                resultList.currentIndex = i;
                resultList.positionViewAtIndex(i, ListView.Contain);
                return;
            }
        }
    }

    function open(result) {
        if (!result) {
            return;
        }
        if (result.kind === "sum") {
            clipboard.text = Search.showAnswer(sumAnswer, frenchComma);
            clipboard.selectAll();
            clipboard.copy();
            copied = true;
            tear();
        } else if (result.kind === "app") {
            activate(allAppsModel, result.row);
        } else if (result.kind === "runner") {
            activate(runnerModel, result.row);
        }
    }

    // On the text field, not onQueryChanged: main.qml has its own handler for that
    Connections {
        target: searchField
        function onTextChanged() { root.queryEdited(); }
    }
    function queryEdited() {
        copied = false;
        rebuild();
        if (sum !== "" && sum !== sumAsked) {
            sumTimer.restart();
        }
    }
    onSumAnswerChanged: rebuild()
    onSumAskedChanged: rebuild()
    onLangChanged: rebuild()
    Timer {
        id: sumTimer
        interval: 120
        onTriggered: if (root.sum !== "") root.sumRequested(root.sum)
    }

    TextEdit { id: clipboard; visible: false }

    // ── Pin / unpin menu ───────────────────────────────────────
    QQC.Popup {
        id: pinMenu
        property string favoriteId
        padding: 4
        background: Rectangle {
            color: Theme.panel2; radius: Theme.radius
            border.width: 1; border.color: Theme.line2
        }
        contentItem: SButton {
            text: root.isPinned(pinMenu.favoriteId) ? root.t("unpin") : root.t("pin")
            onClicked: {
                if (root.isPinned(pinMenu.favoriteId)) {
                    root.unpinRequested(pinMenu.favoriteId);
                } else {
                    root.pinRequested(pinMenu.favoriteId);
                }
                pinMenu.close();
                root.tear();
            }
        }
    }
    function menuFor(favoriteId, item, x, y) {
        if (!favoriteId) {
            return;
        }
        pinMenu.favoriteId = favoriteId;
        const p = item.mapToItem(root, x, y);
        pinMenu.x = Math.min(p.x, root.width - 220);
        pinMenu.y = p.y;
        pinMenu.open();
    }

    // ── Look ──────────────────────────────────────────────────
    Rectangle {
        id: panelBg
        anchors.fill: parent
        color: Theme.bg
        radius: Theme.radius
        border.width: 1
        border.color: Theme.line
    }
    // The panel's frame, slipped: shown for a moment when the launcher tears
    Item {
        id: slipFrame
        anchors.fill: parent
        visible: false
        property real off: 4
        Rectangle { anchors.fill: parent; anchors.leftMargin: slipFrame.off; anchors.rightMargin: -slipFrame.off
                    color: "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.chA }
        Rectangle { anchors.fill: parent; anchors.leftMargin: -slipFrame.off; anchors.rightMargin: slipFrame.off
                    color: "transparent"; radius: Theme.radius; border.width: 1; border.color: Theme.chB }
    }
    SequentialAnimation {
        id: frameSlip
        PropertyAction { target: slipFrame; property: "visible"; value: true }
        NumberAnimation { target: slipFrame; property: "off"; from: 5; to: -3; duration: 90 }
        NumberAnimation { target: slipFrame; property: "off"; to: 2; duration: 80 }
        PropertyAction { target: slipFrame; property: "visible"; value: false }
    }

    Keys.forwardTo: [searchField]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12

        // ── Header: wordmark and search ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            SlipText {
                id: wordmark
                text: "SPARKOS"
                motion: root.motion
                font.family: "Chakra Petch"
                font.pixelSize: 16
                font.letterSpacing: 4
                Layout.alignment: Qt.AlignVCenter
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 34
                radius: Theme.radius
                color: Theme.panel
                border.width: 1
                border.color: searchField.activeFocus ? Theme.accent : Theme.line2
                Kirigami.Icon {
                    id: searchIcon
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 16; height: 16
                    source: "search"
                    color: Theme.muted
                    isMask: true
                }
                TextInput {
                    id: searchField
                    objectName: "searchField"
                    anchors.left: searchIcon.right; anchors.leftMargin: 8
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.text
                    selectionColor: Theme.line2
                    selectedTextColor: Theme.text
                    font.family: Theme.mono
                    font.pixelSize: 13
                    focus: true
                    clip: true
                    Accessible.role: Accessible.EditableText
                    Accessible.name: root.t("search")
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        visible: searchField.text === ""
                        text: root.t("search")
                        color: Theme.dim
                        font: searchField.font
                        elide: Text.ElideRight
                    }
                    Keys.onDownPressed: root.searching ? root.step(1) : pinnedGrid.forceActiveFocus()
                    Keys.onUpPressed: if (root.searching) root.step(-1)
                    Keys.onReturnPressed: root.open(root.results[resultList.currentIndex])
                    Keys.onEnterPressed: root.open(root.results[resultList.currentIndex])
                    Keys.onEscapePressed: {
                        if (root.confirming !== "") {
                            root.confirming = "";
                        } else if (text !== "") {
                            text = "";
                        } else {
                            root.closeRequested();
                        }
                    }
                }
            }
        }

        // ── Search results ──
        ListView {
            id: resultList
            objectName: "resultList"
            visible: root.searching
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.results
            boundsBehavior: Flickable.StopAtBounds
            highlightFollowsCurrentItem: false
            spacing: 1
            delegate: ItemRow {
                required property var modelData
                required property int index
                width: ListView.view.width
                heading: modelData.kind === "heading"
                big: modelData.kind !== "heading"
                name: modelData.name
                description: modelData.description || ""
                icon: modelData.icon
                current: index === resultList.currentIndex
                badge: modelData.kind === "sum" ? (root.copied ? root.t("copied") : root.t("sumHint")) : ""
                onActivated: root.open(modelData)
                onMenuRequested: (x, y) => { if (modelData.kind === "app") root.menuFor(modelData.id, this, x, y) }
            }
            Text {
                anchors.top: parent.top
                anchors.topMargin: 16
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width - 40
                horizontalAlignment: Text.AlignHCenter
                visible: root.searching && root.results.length === 0 && !root.runnerBusy
                text: root.t("nothing", root.query.trim())
                color: Theme.muted
                font.family: Theme.mono
                font.pixelSize: 12
                wrapMode: Text.Wrap
                onVisibleChanged: if (visible) root.tear()
            }
        }

        // ── Pinned ──
        ColumnLayout {
            visible: !root.searching
            Layout.fillWidth: true
            spacing: 6
            Label { text: root.t("pinned") }
            GridView {
                id: pinnedGrid
                objectName: "pinnedGrid"
                Layout.fillWidth: true
                readonly property int columns: 7
                cellWidth: Math.floor(width / columns)
                cellHeight: 76
                Layout.preferredHeight: Math.max(1, Math.min(2, Math.ceil(count / columns))) * cellHeight
                clip: true
                interactive: count > columns * 2
                boundsBehavior: Flickable.StopAtBounds
                model: root.favoritesModel
                currentIndex: -1
                keyNavigationEnabled: true
                Keys.onReturnPressed: if (currentIndex >= 0) root.activate(model, currentIndex)
                Keys.onUpPressed: event => { if (currentIndex < columns) searchField.forceActiveFocus(); else event.accepted = false; }
                onActiveFocusChanged: if (activeFocus && currentIndex < 0) currentIndex = 0
                delegate: AppTile {
                    required property int index
                    required property var model
                    width: GridView.view.cellWidth
                    height: GridView.view.cellHeight
                    name: model.display || ""
                    icon: model.decoration
                    current: GridView.view.activeFocus && GridView.isCurrentItem
                    onActivated: root.activate(GridView.view.model, index)
                    onMenuRequested: (x, y) => root.menuFor(model.favoriteId, this, x, y)
                }
                Text {
                    anchors.fill: parent
                    visible: pinnedGrid.count === 0
                    verticalAlignment: Text.AlignVCenter
                    text: root.t("noPinned")
                    color: Theme.dim
                    font.family: Theme.mono
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
            }
        }

        Rectangle { visible: !root.searching; Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }

        // ── All apps by category | recent files ──
        RowLayout {
            visible: !root.searching
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6
                Label { text: root.t("allApps") }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8
                    ListView {
                        id: categoryList
                        objectName: "categoryList"
                        Layout.preferredWidth: 150
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: root.categoriesModel
                        delegate: Item {
                            id: cat
                            required property int index
                            required property var model
                            readonly property bool chosen: root.category === index
                            width: ListView.view.width
                            height: model.isSeparator === true ? 9 : 26
                            Rectangle {
                                visible: cat.model.isSeparator === true
                                anchors.centerIn: parent; width: parent.width - 8; height: 1; color: Theme.line
                            }
                            Rectangle {
                                anchors.fill: parent
                                visible: cat.model.isSeparator !== true && (cat.chosen || catMouse.containsMouse)
                                radius: Theme.radius
                                color: cat.chosen ? Theme.panel2 : Theme.hover
                                border.width: cat.chosen ? 1 : 0
                                border.color: Theme.line2
                            }
                            Rectangle { visible: cat.chosen; x: 0; y: 5; width: 2; height: parent.height - 10; color: Theme.accent }
                            Text {
                                visible: cat.model.isSeparator !== true
                                x: 10; width: parent.width - 14
                                anchors.verticalCenter: parent.verticalCenter
                                text: cat.model.display || ""
                                color: cat.chosen ? Theme.accent : (catMouse.containsMouse ? Theme.text : Theme.muted)
                                font.family: Theme.mono
                                font.pixelSize: 11
                                font.bold: cat.chosen
                                elide: Text.ElideRight
                            }
                            MouseArea {
                                id: catMouse
                                anchors.fill: parent
                                enabled: cat.model.isSeparator !== true
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.category = cat.index
                            }
                        }
                    }
                    Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.line }
                    ListView {
                        id: appList
                        objectName: "appList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        // Re-read when the category changes (modelForRow makes no binding of its own).
                        // Row 0 is bound to allAppsModel, which main.qml sets again once Plasma's
                        // models fill on the first open; before that modelForRow(0) is null and the
                        // list would stay empty until another category was clicked.
                        model: !root.categoriesModel ? null
                             : root.category === 0 ? root.allAppsModel
                             : root.categoryModelFor(root.category)
                        QQC.ScrollBar.vertical: QQC.ScrollBar { policy: QQC.ScrollBar.AsNeeded }
                        delegate: ItemRow {
                            required property int index
                            required property var model
                            width: ListView.view.width - 8
                            heading: model.isSeparator === true
                            name: heading ? "" : (model.display || "")
                            icon: model.decoration
                            onActivated: root.activate(ListView.view.model, index)
                            onMenuRequested: (x, y) => root.menuFor(model.favoriteId, this, x, y)
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: appList.count === 0
                            text: root.t("empty")
                            color: Theme.dim
                            font.family: Theme.mono
                            font.pixelSize: 11
                        }
                    }
                }
            }

            Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.line }

            ColumnLayout {
                Layout.preferredWidth: 220
                Layout.maximumWidth: 220
                Layout.fillHeight: true
                spacing: 6
                Label { text: root.t("recent") }
                ListView {
                    id: recentList
                    objectName: "recentList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: root.recentModel
                    delegate: ItemRow {
                        required property int index
                        required property var model
                        width: ListView.view.width
                        name: model.display || ""
                        description: model.description || ""
                        icon: model.decoration
                        big: true
                        onActivated: root.activate(ListView.view.model, index)
                    }
                    Text {
                        anchors.top: parent.top; anchors.topMargin: 6
                        width: parent.width
                        visible: recentList.count === 0
                        text: root.t("noRecent")
                        color: Theme.dim
                        font.family: Theme.mono
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line }

        // ── Footer: the store link and the power buttons, or the confirmation ──
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.confirming === ""
            SButton {
                text: root.t("findMore")
                tip: root.t("findMoreTip")
                iconName: "dev.wolklaw.SparkStore"
                visible: root.store !== null
                onClicked: root.activate(root.allAppsModel, root.store.row)
            }
            Item { Layout.fillWidth: true }
            SButton { objectName: "lockButton"; text: root.t("lock"); iconName: "system-lock-screen"; onClicked: root.powerRequested("lock") }
            SButton { objectName: "sleepButton"; text: root.t("sleep"); iconName: "system-suspend"; visible: root.canSuspend; onClicked: root.powerRequested("sleep") }
            SButton { objectName: "logoutButton"; text: root.t("signOut"); iconName: "system-log-out"; onClicked: root.ask("logout") }
            SButton { objectName: "restartButton"; text: root.t("restart"); iconName: "system-reboot"; onClicked: root.ask("restart") }
            SButton { objectName: "shutdownButton"; text: root.t("shutDown"); iconName: "system-shutdown"; kind: "danger"; onClicked: root.ask("shutdown") }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            visible: root.confirming !== ""
            SlipText {
                id: question
                Layout.fillWidth: true
                motion: root.motion
                rest: 1
                color: Theme.text
                font.pixelSize: 12
                text: root.confirming === "restart" ? root.t("confirmRestart")
                    : root.confirming === "shutdown" ? root.t("confirmShutDown")
                    : root.confirming === "logout" ? root.t("confirmSignOut") : ""
            }
            SButton {
                objectName: "cancelButton"
                text: root.t("cancel")
                onClicked: root.confirming = ""
            }
            SButton {
                id: confirmButton
                objectName: "confirmButton"
                kind: "danger"
                text: root.confirming === "restart" ? root.t("restart")
                    : root.confirming === "shutdown" ? root.t("shutDown") : root.t("signOut")
                onClicked: {
                    const what = root.confirming;
                    root.confirming = "";
                    root.powerRequested(what);
                }
            }
        }
    }

    function ask(what) {
        confirming = what;
        confirmButton.forceActiveFocus();
        question.tear();
        tear();
    }

    // One row of a model, read into plain properties (apps for the search box, KRunner's results)
    component AppEntry: QtObject {
        required property int index
        required property var model
        readonly property string name: model.display || ""
        readonly property var icon: model.decoration
        readonly property string description: model.description || ""
        readonly property string id: model.favoriteId || ""
        readonly property string group: model.group || ""
        readonly property bool separator: model.isSeparator === true
        readonly property int row: index
    }

    component Label: Text {
        color: Theme.dim
        font.family: Theme.mono
        font.pixelSize: 10
        font.bold: true
        font.letterSpacing: 1.5
    }
}
