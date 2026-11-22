// A pinned app: its icon over its name. Click opens it, right-click offers Unpin.
import QtQuick
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme

Item {
    id: root

    property string name
    property var icon
    property bool current: false
    readonly property bool lit: mouse.containsMouse || current

    signal activated()
    signal menuRequested(real x, real y)

    Accessible.role: Accessible.Button
    Accessible.name: name

    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        radius: Theme.radius
        color: root.lit ? Theme.hover : "transparent"
        border.width: root.lit ? 1 : 0
        border.color: Theme.line2
    }
    // The split along the bottom edge when lit
    Rectangle {
        x: 8; width: parent.width - 13; height: 2; y: parent.height - 4
        color: Theme.chA; visible: root.lit
    }
    Rectangle {
        x: 5; width: parent.width - 13; height: 2; y: parent.height - 4
        color: Theme.chB; visible: root.lit; opacity: 0.9
    }

    Kirigami.Icon {
        id: image
        anchors.horizontalCenter: parent.horizontalCenter
        y: 8
        width: 36; height: 36
        source: root.icon
        active: root.lit
    }
    Text {
        anchors.top: image.bottom
        anchors.topMargin: 5
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: 4; anchors.rightMargin: 4
        text: root.name
        color: root.lit ? Theme.text : Theme.muted
        font.family: Theme.mono
        font.pixelSize: 10
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        maximumLineCount: 1
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
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
