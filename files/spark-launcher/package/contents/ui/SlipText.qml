// Text with the house fault: a magenta and a cyan copy slipped out of register behind it.
// The 1-2 px slip stays; tear() makes it jump for a quarter of a second.
import QtQuick
import "../code/theme.js" as Theme

Item {
    id: root

    property alias text: label.text
    property alias font: label.font
    property color color: Theme.text
    property real rest: 1.5
    property real slip: rest
    property bool motion: true

    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight

    function tear() {
        if (motion) {
            burst.restart();
        }
    }

    Text {
        x: root.slip
        text: label.text; font: label.font; color: Theme.chA; opacity: 0.85
        width: label.width; elide: label.elide
    }
    Text {
        x: -root.slip
        text: label.text; font: label.font; color: Theme.chB; opacity: 0.85
        width: label.width; elide: label.elide
    }
    Text {
        id: label
        width: root.width > 0 ? root.width : implicitWidth
        color: root.color
        elide: Text.ElideRight
        font.family: Theme.mono
        font.bold: true
    }

    SequentialAnimation {
        id: burst
        NumberAnimation { target: root; property: "slip"; to: 6; duration: 50 }
        NumberAnimation { target: root; property: "slip"; to: -4; duration: 50 }
        NumberAnimation { target: root; property: "slip"; to: 3; duration: 60 }
        NumberAnimation { target: root; property: "slip"; to: root.rest; duration: 90 }
    }
}
