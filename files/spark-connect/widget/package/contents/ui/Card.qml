// A panel with the house fault: anything that isn't fine gets a magenta and a cyan edge slipped
// out of register behind it (as the window's cards do); tear() makes it jump.
import QtQuick
import "../code/theme.js" as Theme

Item {
    id: root

    default property alias content: body.data
    property bool trouble: false
    property bool motion: true
    property bool hovered: false
    property real slip: trouble ? 2 : 0
    property real pad: 10

    implicitHeight: body.childrenRect.height + pad * 2

    function tear() {
        if (motion) {
            burst.restart();
        }
    }

    Rectangle {
        anchors.fill: parent; anchors.leftMargin: root.slip; anchors.rightMargin: -root.slip
        radius: Theme.radius; color: Theme.chA; visible: root.slip !== 0; opacity: 0.8
    }
    Rectangle {
        anchors.fill: parent; anchors.leftMargin: -root.slip; anchors.rightMargin: root.slip
        radius: Theme.radius; color: Theme.chB; visible: root.slip !== 0; opacity: 0.8
    }
    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: root.hovered ? Theme.hover : Theme.panel
        border.color: root.hovered ? Theme.line2 : Theme.line
        border.width: 1
    }
    Item {
        id: body
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: root.pad }
        height: childrenRect.height
    }

    SequentialAnimation {
        id: burst
        NumberAnimation { target: root; property: "slip"; to: 5; duration: 50 }
        NumberAnimation { target: root; property: "slip"; to: -4; duration: 50 }
        NumberAnimation { target: root; property: "slip"; to: 3; duration: 60 }
        NumberAnimation { target: root; property: "slip"; to: root.trouble ? 2 : 0; duration: 90 }
    }
}
