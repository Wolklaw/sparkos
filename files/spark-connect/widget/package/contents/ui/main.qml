// Spark Connect as a Plasma widget. On a panel: the app's icon with a status dot (cyan all
// good, gold a warning, magenta something down); a click opens the board. On the desktop: the
// board itself. Every refreshSeconds it runs `spark-connect --status` (one probe per machine
// over the same SSH as the window, one GET per website) and shows what it says. It never
// fixes anything; the board's button opens the window for that.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import "../code/theme.js" as Theme
import "../code/status.js" as Status

PlasmoidItem {
    id: widget

    property var report: null
    property bool busy: false
    readonly property string level: report ? report.level : "warn"
    readonly property bool motion: Kirigami.Units.longDuration > 0

    function refresh() {
        if (busy) {
            return;                       // the last check is still running (a slow machine)
        }
        busy = true;
        runner.connectSource(Status.statusCommand);
    }

    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            disconnectSource(source);
            if (source !== Status.statusCommand) {
                return;                   // the open command
            }
            widget.report = Status.parse(data.stdout, data["exit code"]);
            widget.busy = false;
            if (widget.level !== "ok") {
                widget.tearSoon();
            }
        }
    }
    function openApp() {
        runner.connectSource(Status.openCommand);
        widget.expanded = false;
    }

    // The board tears when an answer isn't fine; it may not exist yet (a closed popup)
    function tearSoon() {
        if (fullRepresentationItem) {
            (fullRepresentationItem as Board).tear();
        }
    }

    Timer {
        interval: Math.max(15, Plasmoid.configuration.refreshSeconds) * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: widget.refresh()
    }

    Plasmoid.icon: "dev.wolklaw.SparkConnect"
    Plasmoid.status: level === "ok" ? PlasmaCore.Types.ActiveStatus : PlasmaCore.Types.NeedsAttentionStatus
    toolTipMainText: "Spark Connect"
    toolTipSubText: report ? report.summary + (report.checked ? "\n" + report.checked : "") : ""
    preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
    switchWidth: Kirigami.Units.gridUnit * 14
    switchHeight: Kirigami.Units.gridUnit * 10
    onExpandedChanged: {
        if (expanded && report && level !== "ok") {
            tearSoon();
        }
    }

    // ── On a panel ─────────────────────────────────────────────
    compactRepresentation: MouseArea {
        id: button
        readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
        readonly property real iconSize: Math.min(vertical ? width : height, Kirigami.Units.iconSizes.huge)
        property bool wasExpanded
        Layout.preferredWidth: vertical ? -1 : iconSize
        Layout.preferredHeight: vertical ? iconSize : -1
        hoverEnabled: true
        Accessible.name: "Spark Connect: " + (widget.report ? widget.report.summary : "")
        Accessible.role: Accessible.Button
        onPressed: wasExpanded = widget.expanded
        onClicked: widget.expanded = !wasExpanded

        Kirigami.Icon {
            anchors.centerIn: parent
            width: button.iconSize
            height: button.iconSize
            source: Plasmoid.icon
            active: button.containsMouse || widget.expanded
        }
        // The status dot, bottom right, on the panel's own background so it reads on any icon
        Rectangle {
            readonly property real d: Math.max(6, Math.round(button.iconSize * 0.34))
            width: d; height: d; radius: d / 2
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: Math.max(0, (button.width - button.iconSize) / 2)
            color: widget.report ? Status.colour(widget.level, Theme) : Theme.dim
            border.color: Theme.bg
            border.width: Math.max(1, Math.round(d / 6))
        }
    }

    // ── Open, or on the desktop ────────────────────────────────
    fullRepresentation: Board {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.minimumHeight: Kirigami.Units.gridUnit * 10
        Layout.preferredWidth: implicitWidth
        Layout.preferredHeight: implicitHeight
        report: widget.report
        busy: widget.busy && !widget.report
        motion: widget.motion
        onOpenApp: widget.openApp()
    }
}
