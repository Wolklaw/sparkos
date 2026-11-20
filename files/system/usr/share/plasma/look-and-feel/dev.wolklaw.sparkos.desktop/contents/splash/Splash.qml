// SparkOS splash, shown while Plasma starts after sign-in: the SparkOS bot, the spaced
// wordmark with its magenta/cyan slip, and a thin mint progress line.
import QtQuick 2.15

Rectangle {
    id: root
    color: "#05040f"

    // Set by ksplash as Plasma starts (1 to 6)
    property int stage

    readonly property color mint: "#9be8b8"
    readonly property color channelA: "#ff2e88"
    readonly property color channelB: "#22d8ff"

    Column {
        anchors.centerIn: parent
        spacing: 26

        Image {
            id: bot
            anchors.horizontalCenter: parent.horizontalCenter
            source: "images/bot.png"
            width: 280
            height: 280
            smooth: true
            mipmap: true
        }

        // Wordmark: the text three times, the two channel copies slipped sideways
        Item {
            id: wordmark
            anchors.horizontalCenter: parent.horizontalCenter
            width: label.implicitWidth
            height: label.implicitHeight

            property real slip: 3

            Text {
                x: wordmark.slip
                text: label.text; font: label.font; color: root.channelA; opacity: 0.9
            }
            Text {
                x: -wordmark.slip
                text: label.text; font: label.font; color: root.channelB; opacity: 0.9
            }
            Text {
                id: label
                text: "SPARKOS"
                color: "#f1efff"
                font.family: "Chakra Petch"
                font.weight: Font.Bold
                font.pixelSize: 34
                font.letterSpacing: 11
            }

            // One short tear when Plasma is nearly ready, then back to the resting slip
            SequentialAnimation {
                id: tear
                NumberAnimation { target: wordmark; property: "slip"; to: 9; duration: 70 }
                NumberAnimation { target: wordmark; property: "slip"; to: -5; duration: 60 }
                NumberAnimation { target: wordmark; property: "slip"; to: 3; duration: 90 }
            }
        }

        Rectangle {
            id: track
            anchors.horizontalCenter: parent.horizontalCenter
            width: 260
            height: 3
            color: Qt.rgba(236 / 255, 233 / 255, 255 / 255, 0.14)

            Rectangle {
                height: parent.height
                width: parent.width * Math.min(root.stage, 6) / 6
                color: root.mint
                Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
            }
        }
    }

    onStageChanged: {
        if (stage === 5) {
            tear.start()
        }
    }
}
