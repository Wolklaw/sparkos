// One row in a list: an app, a search result or a recent file. A row can also be a small
// section heading (heading: true), which isn't clickable.
import QtQuick
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme

Item {
    id: root

    property string name
    property string description
    property var icon
    property bool heading: false
    property bool current: false
    property bool big: false
    property string badge
    readonly property bool lit: !heading && (mouse.containsMouse || current)

    signal activated()
    signal menuRequested(real x, real y)

    implicitHeight: heading ? 24 : (big ? 40 : 30)
    Accessible.role: heading ? Accessible.StaticText : Accessible.ListItem
    Accessible.name: name
    Accessible.description: description

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        visible: root.lit
        color: Theme.hover
        border.width: 1
        border.color: Theme.line2
    }
    Rectangle {
        visible: root.lit
        x: 0; width: 2; height: parent.height - 8; y: 4
        color: Theme.chB
    }
    Rectangle {
        visible: root.lit
        x: 3; width: 2; height: parent.height - 8; y: 4
        color: Theme.chA
    }

    Kirigami.Icon {
        id: image
        visible: !root.heading
        x: 10
        anchors.verticalCenter: parent.verticalCenter
        width: root.big ? 26 : 20; height: width
        source: root.icon
        active: root.lit
    }
    Column {
        anchors.left: root.heading ? parent.left : image.right
        anchors.leftMargin: root.heading ? 4 : 10
        anchors.right: badgeText.visible ? badgeText.left : parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1
        Text {
            width: parent.width
            text: root.name
            color: root.heading ? Theme.dim : (root.lit ? Theme.text : "#b9ddd6")
            font.family: Theme.mono
            font.pixelSize: root.heading ? 10 : 12
            font.bold: root.heading
            font.letterSpacing: root.heading ? 1 : 0
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            visible: root.big && root.description !== ""
            text: root.description
            color: Theme.muted
            font.family: Theme.mono
            font.pixelSize: 10
            elide: Text.ElideMiddle
        }
    }
    Text {
        id: badgeText
        visible: root.badge !== ""
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: root.badge
        color: Theme.dim
        font.family: Theme.mono
        font.pixelSize: 10
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: !root.heading
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: mouse => {
            if (mouse.button === Qt.RightButton) {
                root.menuRequested(mouse.x, mouse.y);
            } else {
                root.activated();
            }
        }
    }
}
