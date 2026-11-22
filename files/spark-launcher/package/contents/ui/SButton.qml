// A flat Spark button: outlined (ghost), filled in the accent (primary) or pink (danger).
// Hover and keyboard focus show the channel split behind it.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme

Item {
    id: root

    property string text
    property string iconName
    property string kind: "ghost"   // ghost, primary, danger
    property string tip
    readonly property bool lit: mouse.containsMouse || activeFocus

    signal clicked()

    implicitWidth: row.implicitWidth + 20
    implicitHeight: 30
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: tip
    Accessible.onPressAction: clicked()
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()
    Keys.onSpacePressed: clicked()

    // The split: two copies of the frame, slipped sideways
    Rectangle {
        anchors.fill: face; anchors.leftMargin: 3; anchors.rightMargin: -3
        radius: Theme.radius; color: Theme.chA; visible: root.lit
    }
    Rectangle {
        anchors.fill: face; anchors.leftMargin: -3; anchors.rightMargin: 3
        radius: Theme.radius; color: Theme.chB; visible: root.lit
    }
    Rectangle {
        id: face
        anchors.fill: parent
        radius: Theme.radius
        color: root.kind === "primary" ? (root.lit ? Theme.accentHover : Theme.accent)
             : root.kind === "danger" ? (root.lit ? "#ff7aa8" : Theme.pink)
             : (root.lit ? Theme.hover : Theme.panel)
        border.width: root.kind === "ghost" ? 1 : 0
        border.color: root.lit ? Theme.line2 : Theme.line
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Kirigami.Icon {
            source: root.iconName
            visible: root.iconName !== ""
            implicitWidth: 16; implicitHeight: 16
            color: label.color
            isMask: true
        }
        Text {
            id: label
            text: root.text
            visible: root.text !== ""
            color: root.kind === "ghost" ? (root.lit ? Theme.text : Theme.muted) : Theme.onAccent
            font.family: Theme.mono
            font.bold: true
            font.pixelSize: 11
            font.letterSpacing: 0.5
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    QQC.ToolTip.text: root.tip
    QQC.ToolTip.visible: root.tip !== "" && mouse.containsMouse
    QQC.ToolTip.delay: 600
}
