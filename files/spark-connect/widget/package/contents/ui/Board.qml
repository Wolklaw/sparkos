// The open widget: the window's overview, smaller. One card per machine (state, verdict, the
// five numbers), one row per website. Anything that isn't fine sorts first and slips; a calm
// board has no fault on it. Clicking anywhere opens Spark Connect.
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "../code/theme.js" as Theme
import "../code/status.js" as Status

Rectangle {
    id: board

    property var report: null
    property bool busy: false
    property bool motion: true
    signal openApp()

    readonly property var machines: sorted(report ? report.machines : [])
    readonly property var sites: sorted(report ? report.sites : [])
    readonly property string level: report ? report.level : "warn"

    function sorted(list) {
        // worst first, then the config's order
        return list.map((item, i) => ({ item: item, i: i }))
                   .sort((a, b) => Status.LEVELS.indexOf(a.item.level) - Status.LEVELS.indexOf(b.item.level) || a.i - b.i)
                   .map(x => x.item);
    }
    function label(key, fallback) { return Status.label(report, key, fallback); }

    // A new answer that isn't fine tears the heading and every card in trouble
    function tear() {
        title.tear();
        for (let i = 0; i < cards.count; i++) {
            const c = cards.itemAt(i) as Card;
            if (c && c.trouble) c.tear();
        }
        for (let i = 0; i < siteRows.count; i++) {
            const c = siteRows.itemAt(i) as Card;
            if (c && c.trouble) c.tear();
        }
    }

    implicitWidth: 400
    implicitHeight: Math.min(column.implicitHeight + 24, 860)
    color: Theme.bg
    radius: Theme.radius

    Flickable {
        anchors.fill: parent
        anchors.margins: 12
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: column
            width: parent.width
            spacing: 6

            // ── Heading ──────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                SlipText {
                    id: title
                    text: "SPARK CONNECT"
                    font.family: "Chakra Petch"
                    font.pixelSize: 16
                    font.letterSpacing: 1.5
                    motion: board.motion
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: board.busy ? "…" : (board.report && board.report.checked ? board.report.checked : "")
                    color: Theme.dim
                    font.family: Theme.mono
                    font.pixelSize: 10
                }
            }
            Text {
                Layout.fillWidth: true
                text: "● " + (board.report ? String(board.report.summary).toUpperCase() : "…")
                color: board.report ? Status.colour(board.level, Theme) : Theme.muted
                font.family: Theme.mono
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideRight
            }
            Text {
                visible: !!(board.report && board.report.error)
                Layout.fillWidth: true
                text: board.report && board.report.error ? board.report.error : ""
                color: Theme.muted
                font.family: Theme.mono
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.line; Layout.topMargin: 2 }

            // ── Machines ─────────────────────────────────
            Text {
                visible: board.machines.length > 0
                text: board.label("overview.machines", "Machines").toUpperCase() + "  " + board.machines.length
                color: Theme.muted; font.family: Theme.mono; font.pixelSize: 9; font.bold: true
                Layout.topMargin: 4
            }
            Repeater {
                id: cards
                model: board.machines
                delegate: Card {
                    id: card
                    required property var modelData
                    Layout.fillWidth: true
                    trouble: modelData.level !== "ok"
                    motion: board.motion
                    hovered: cardMouse.containsMouse
                    pad: 9

                    ColumnLayout {
                        width: parent.width
                        spacing: 3
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: card.modelData.name
                                color: Theme.text; font.family: Theme.mono; font.pixelSize: 13; font.bold: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: "● " + card.modelData.state
                                color: Status.colour(card.modelData.level, Theme)
                                font.family: Theme.mono; font.pixelSize: 9; font.bold: true
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: card.modelData.verdict + (card.modelData.more > 0 ? "  +" + card.modelData.more : "")
                            color: Status.colour(card.modelData.level, Theme)
                            font.family: Theme.mono; font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                        GridLayout {
                            visible: card.modelData.up
                            Layout.topMargin: 3
                            columns: 5
                            rowSpacing: 0
                            columnSpacing: 12
                            Repeater {
                                model: [["card.uptime", "UP FOR"], ["card.load", "LOAD"], ["card.memory", "MEMORY"],
                                        ["card.disk", "DISK"], ["card.temp", "TEMP"]]
                                delegate: Text {
                                    required property var modelData
                                    text: board.label(modelData[0], modelData[1])
                                    color: Theme.muted; font.family: Theme.mono; font.pixelSize: 8; font.bold: true
                                }
                            }
                            Repeater {
                                model: ["uptime", "load", "memory", "disk", "temp"]
                                delegate: Text {
                                    required property string modelData
                                    text: card.modelData[modelData]
                                    color: Theme.text; font.family: Theme.mono; font.pixelSize: 11
                                }
                            }
                        }
                    }
                    MouseArea {
                        id: cardMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: board.openApp()
                    }
                }
            }

            // ── Websites ─────────────────────────────────
            Text {
                visible: board.sites.length > 0
                text: board.label("overview.sites", "Websites").toUpperCase() + "  " + board.sites.length
                color: Theme.muted; font.family: Theme.mono; font.pixelSize: 9; font.bold: true
                Layout.topMargin: 6
            }
            Repeater {
                id: siteRows
                model: board.sites
                delegate: Card {
                    id: row
                    required property var modelData
                    Layout.fillWidth: true
                    trouble: !modelData.ok
                    motion: board.motion
                    hovered: rowMouse.containsMouse
                    pad: 6

                    RowLayout {
                        width: parent.width
                        spacing: 8
                        Text {
                            text: "●"
                            color: Status.colour(row.modelData.level, Theme)
                            font.family: Theme.mono; font.pixelSize: 9
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.name
                            color: Theme.text; font.family: Theme.mono; font.pixelSize: 11; font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: row.modelData.status
                            color: Status.colour(row.modelData.level, Theme)
                            font.family: Theme.mono; font.pixelSize: 11; font.bold: true
                            elide: Text.ElideRight
                            Layout.maximumWidth: 150
                        }
                        Text {
                            text: row.modelData.ms
                            color: Theme.muted; font.family: Theme.mono; font.pixelSize: 11
                            horizontalAlignment: Text.AlignRight
                            Layout.preferredWidth: 52
                        }
                    }
                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: board.openApp()
                    }
                }
            }

            // ── Open the window ──────────────────────────
            Rectangle {
                id: open
                Layout.fillWidth: true
                Layout.topMargin: 6
                implicitHeight: 28
                radius: Theme.radius
                color: openMouse.containsMouse ? Theme.accentHover : Theme.accent
                // the split shadow on hover and focus, as every Spark button has
                Rectangle { z: -1; anchors.fill: parent; anchors.leftMargin: 3; anchors.rightMargin: -3; radius: Theme.radius; color: Theme.chA; visible: openMouse.containsMouse }
                Rectangle { z: -1; anchors.fill: parent; anchors.leftMargin: -3; anchors.rightMargin: 3; radius: Theme.radius; color: Theme.chB; visible: openMouse.containsMouse }
                Text {
                    anchors.centerIn: parent
                    text: board.label("widget.open", "Open Spark Connect").toUpperCase()
                    color: Theme.onAccent; font.family: Theme.mono; font.pixelSize: 10; font.bold: true
                }
                MouseArea {
                    id: openMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: board.openApp()
                }
            }
        }
    }
}
