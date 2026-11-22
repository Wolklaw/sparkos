// search.js and strings.js on their own: ranking, sum detection, the French table.
import QtQuick
import QtTest
import "../package/contents/code/search.js" as Search
import "../package/contents/code/strings.js" as Strings

TestCase {
    name: "Search"

    readonly property var apps: [
        { name: "Firefox", description: "Web Browser", id: "org.mozilla.firefox.desktop" },
        { name: "Spark Calc", description: "Calculator", id: "dev.wolklaw.SparkCalc.desktop" },
        { name: "Spark Monitor", description: "Task manager", id: "dev.wolklaw.SparkMonitor.desktop" },
        { name: "Paramètres système", description: "Réglages", id: "systemsettings.desktop" },
        { name: "Calendar", description: "Agenda", id: "org.kde.merkuro.calendar.desktop" },
    ]

    function names(list) { return list.map(a => a.name); }

    function test_prefix_beats_word_beats_contains() {
        compare(names(Search.filterApps(apps, "cal")), ["Calendar", "Spark Calc"]);
        compare(names(Search.filterApps(apps, "spark")), ["Spark Calc", "Spark Monitor"]);
    }

    function test_description_and_initials() {
        compare(names(Search.filterApps(apps, "browser")), ["Firefox"]);
        compare(names(Search.filterApps(apps, "sm")), ["Spark Monitor"]);
    }

    function test_accents_and_case() {
        compare(names(Search.filterApps(apps, "PARAMETRES")), ["Paramètres système"]);
    }

    function test_empty_and_limit() {
        compare(Search.filterApps(apps, "   ").length, 0);
        compare(Search.filterApps(apps, "zzz").length, 0);
        compare(Search.filterApps(apps, "a", 2).length, 2);
    }

    function test_sums() {
        compare(Search.sumFrom("2+2"), "2+2");
        compare(Search.sumFrom(" = 12 * 3 "), "12 * 3");
        compare(Search.sumFrom("sqrt(2)"), "sqrt(2)");
        compare(Search.sumFrom("sin(30) + cos(60)"), "sin(30) + cos(60)");
        compare(Search.sumFrom("200 + 10%"), "200 + 10%");
        compare(Search.sumFrom("5!"), "5!");
        compare(Search.sumFrom("2π"), "2π");
        compare(Search.sumFrom("10 - 3"), "10 - 3");
        compare(Search.sumFrom("1,5 + 2", true), "1.5 + 2");
    }

    function test_not_sums() {
        compare(Search.sumFrom("firefox"), "");
        compare(Search.sumFrom("42"), "");
        compare(Search.sumFrom("-5"), "");
        compare(Search.sumFrom("spark 2"), "");
        compare(Search.sumFrom("calc"), "");
        compare(Search.sumFrom("2+2'; rm -rf ~; '"), "");
        compare(Search.sumFrom("$(reboot)+1"), "");
        compare(Search.sumFrom("1+1 && reboot"), "");
        compare(Search.sumFrom("1".repeat(201) + "+1"), "");
    }

    function test_sum_command_is_quoted() {
        compare(Search.sumCommand("2+2"), "timeout 2 spark-calc --eval '2+2'");
        compare(Search.sumCommand("2'+2"), "");
        compare(Search.sumCommand("$HOME"), "");
        compare(Search.sumCommand(""), "");
    }

    function test_answer_in_french() {
        compare(Search.showAnswer("0.3", true), "0,3");
        compare(Search.showAnswer("0.3\n", false), "0.3");
    }

    function test_every_word_has_a_french_one() {
        compare(Strings.language("fr_CA"), "fr");
        compare(Strings.language("de_DE"), "en");
        compare(Strings.keys("fr").sort(), Strings.keys("en").sort());
        compare(Strings.tr("fr", "nothing", "abc"), "Rien trouvé pour « abc ».");
    }
}
