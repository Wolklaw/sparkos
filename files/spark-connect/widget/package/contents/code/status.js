.pragma library
// What the widget runs and how it reads the answer. No QML here, so tests/tst_widget.qml
// checks it on its own.

// ~/.local/bin is not always on the Plasma session's PATH: the --user install puts it there.
const FIND = 'p=$(command -v spark-connect || echo "$HOME/.local/bin/spark-connect"); ';
const statusCommand = FIND + '"$p" --status';
// setsid -f: the window outlives the widget's process and Plasma doesn't wait for it
const openCommand = FIND + 'setsid -f "$p" >/dev/null 2>&1 < /dev/null';

const LEVELS = ["down", "bad", "warn", "ok"];

// spark-connect --status's stdout as an object; a stand-in with an error line when it isn't one
function parse(stdout, exitCode) {
    let report = null;
    try {
        report = JSON.parse(String(stdout));
    } catch (e) {
        report = null;
    }
    if (!report || report.format !== 1) {
        const why = exitCode === 127 ? "spark-connect is not installed"
                  : "spark-connect gave no answer" + (exitCode ? " (exit " + exitCode + ")" : "");
        return { level: "down", summary: why, error: why, machines: [], sites: [], labels: {} };
    }
    if (LEVELS.indexOf(report.level) < 0) {
        report.level = "warn";
    }
    report.machines = report.machines || [];
    report.sites = report.sites || [];
    report.labels = report.labels || {};
    return report;
}

function colour(level, theme) {
    switch (level) {
    case "ok": return theme.accent;
    case "warn": return theme.gold;
    default: return theme.pink;            // bad, down
    }
}

// The label in the PC's language from the report, the English one before the first answer
function label(report, key, fallback) {
    return report && report.labels && report.labels[key] ? report.labels[key] : fallback;
}
