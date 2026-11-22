.pragma library
// Spark Launcher's own logic, kept out of the QML so tests can run it without Plasma:
// ranking apps for the search box, and deciding when the text is a sum for Spark Calc.

// Lower case, accents dropped (so "parametres" finds "Paramètres").
function fold(text) {
    return String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// Score one app against the query; 0 means no match. Higher is better.
//   name starts with the query  > a word in the name starts with it > the name contains it
//   > the description (generic name, "Web Browser") matches > the desktop file id matches.
function score(app, q) {
    const name = fold(app.name);
    if (!q || !name) {
        return 0;
    }
    if (name === q) {
        return 100;
    }
    if (name.startsWith(q)) {
        return 80;
    }
    const words = name.split(/[\s\-_.]+/);
    for (let i = 0; i < words.length; i++) {
        if (words[i].startsWith(q)) {
            return 60;
        }
    }
    if (name.includes(q)) {
        return 40;
    }
    // Initials: "sm" finds Spark Monitor
    if (q.length >= 2 && words.map(w => w.charAt(0)).join("").startsWith(q)) {
        return 30;
    }
    const desc = fold(app.description);
    if (desc && desc.split(/[\s\-_.]+/).some(w => w.startsWith(q))) {
        return 20;
    }
    if (fold(app.id).includes(q)) {
        return 10;
    }
    return 0;
}

// The apps matching the query, best first, at most `limit`. Each app is
// { name, description, id, ... }; the objects are returned as given.
function filterApps(apps, query, limit) {
    const q = fold(query).trim();
    if (!q) {
        return [];
    }
    const hits = [];
    for (let i = 0; i < apps.length; i++) {
        const s = score(apps[i], q);
        if (s > 0) {
            hits.push({ app: apps[i], s: s, i: i });
        }
    }
    hits.sort((a, b) => b.s - a.s || fold(a.app.name).localeCompare(fold(b.app.name)) || a.i - b.i);
    return hits.slice(0, limit || 8).map(h => h.app);
}

// Spark Calc's names (sparkcalc/engine.py FUNCTIONS, CONSTANTS, KEYWORD_OPS).
const CALC_NAMES = [
    "sin", "cos", "tan", "sec", "csc", "cot", "asin", "acos", "atan", "arcsin", "arccos",
    "arctan", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh", "sqrt", "cbrt", "root", "exp",
    "ln", "log", "log2", "log10", "abs", "floor", "ceil", "round", "pi", "e", "mod",
];

// The sum to hand to Spark Calc, or "" if the text isn't one. Only digits, Spark Calc's
// operators and its function names pass, so the result is always safe inside single quotes
// on a command line. A bare number or a plain word is not a sum.
//   frenchComma: "1,5 + 2" means 1.5 + 2 (a comma between digits is the decimal mark)
function sumFrom(text, frenchComma) {
    let t = String(text || "").trim();
    if (t.length === 0 || t.length > 200) {
        return "";
    }
    if (t.startsWith("=")) {
        t = t.slice(1).trim();
    }
    if (!/^[0-9a-zA-Z.,\s+\-*\/^%()!×÷−·√π²³]+$/.test(t)) {
        return "";
    }
    if (!/[0-9π]/.test(t)) {
        return "";
    }
    const names = t.match(/[a-zA-Z]+[0-9]*/g) || [];
    for (let i = 0; i < names.length; i++) {
        const n = names[i].toLowerCase();
        if (CALC_NAMES.indexOf(n) < 0 && CALC_NAMES.indexOf(n.replace(/[0-9]+$/, "")) < 0) {
            return "";
        }
    }
    // Something has to happen: an operator, a function call, a constant or a power sign.
    const hasOp = /[+*\/^%!×÷−·√²³]/.test(t) || /[0-9)]\s*-/.test(t) || /-\s*[0-9(]/.test(t.slice(1));
    if (!hasOp && names.length === 0 && t.indexOf("π") < 0) {
        return "";
    }
    if (frenchComma) {
        t = t.replace(/([0-9]),([0-9])/g, "$1.$2");
    }
    return t;
}

// The command that evaluates a sum. sumFrom() already rejected quotes and shell characters;
// this check stays so a mistake there can't become a shell command.
function sumCommand(sum) {
    if (!sum || /['"`$\\;&|<>\n]/.test(sum)) {
        return "";
    }
    return "timeout 2 spark-calc --eval '" + sum + "'";
}

// Spark Calc writes its answer with a point; French shows a comma.
function showAnswer(answer, frenchComma) {
    const a = String(answer || "").trim();
    return frenchComma ? a.replace(/\./g, ",") : a;
}
