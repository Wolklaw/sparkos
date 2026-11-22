// The open launcher with a fake app list: the search box filters it, Enter opens the right
// row, sums go to Spark Calc, shut down asks first. Saves screenshots for looking at.
import QtQuick
import QtTest
import "../package/contents/ui"

Item {
    id: window
    width: 760
    height: 600

    property string shots: "/tmp/spark-launcher-shots"

    ListModel {
        id: allApps
        ListElement { display: "Firefox"; decoration: "firefox"; description: "Web Browser"; favoriteId: "org.mozilla.firefox.desktop" }
        ListElement { display: "Soot"; decoration: "dev.wolklaw.Soot"; description: "Assistant"; favoriteId: "dev.wolklaw.Soot.desktop" }
        ListElement { display: "Spark Calc"; decoration: "accessories-calculator"; description: "Calculator"; favoriteId: "dev.wolklaw.SparkCalc.desktop" }
        ListElement { display: "Spark Edit"; decoration: "accessories-text-editor"; description: "Text Editor"; favoriteId: "dev.wolklaw.SparkEdit.desktop" }
        ListElement { display: "Spark Games"; decoration: "applications-games"; description: "Game Library"; favoriteId: "dev.wolklaw.SparkGames.desktop" }
        ListElement { display: "Spark Media"; decoration: "multimedia-player"; description: "Media Player"; favoriteId: "dev.wolklaw.SparkMedia.desktop" }
        ListElement { display: "Spark Monitor"; decoration: "utilities-system-monitor"; description: "Task Manager"; favoriteId: "dev.wolklaw.SparkMonitor.desktop" }
        ListElement { display: "Spark Store"; decoration: "system-software-install"; description: "Software Center"; favoriteId: "dev.wolklaw.SparkStore.desktop" }
        ListElement { display: "System Settings"; decoration: "preferences-system"; description: "Settings"; favoriteId: "systemsettings.desktop" }
    }
    ListModel {
        id: categories
        ListElement { display: "All Applications" }
        ListElement { display: "Games" }
        ListElement { display: "Internet" }
        ListElement { display: "Utilities" }
    }
    ListModel {
        id: games
        ListElement { display: "Spark Games"; decoration: "applications-games"; favoriteId: "dev.wolklaw.SparkGames.desktop" }
    }
    ListModel {
        id: pinned
        ListElement { display: "Soot"; decoration: "dev.wolklaw.Soot"; favoriteId: "applications:dev.wolklaw.Soot.desktop" }
        ListElement { display: "Spark Store"; decoration: "system-software-install"; favoriteId: "applications:dev.wolklaw.SparkStore.desktop" }
        ListElement { display: "Spark Games"; decoration: "applications-games"; favoriteId: "applications:dev.wolklaw.SparkGames.desktop" }
        ListElement { display: "Spark Media"; decoration: "multimedia-player"; favoriteId: "applications:dev.wolklaw.SparkMedia.desktop" }
        ListElement { display: "Spark Calc"; decoration: "accessories-calculator"; favoriteId: "applications:dev.wolklaw.SparkCalc.desktop" }
        ListElement { display: "Spark Edit"; decoration: "accessories-text-editor"; favoriteId: "applications:dev.wolklaw.SparkEdit.desktop" }
        ListElement { display: "Spark Monitor"; decoration: "utilities-system-monitor"; favoriteId: "applications:dev.wolklaw.SparkMonitor.desktop" }
    }
    ListModel {
        id: recent
        ListElement { display: "budget-2026.ods"; decoration: "x-office-spreadsheet"; description: "~/Documents" }
        ListElement { display: "notes.txt"; decoration: "text-plain"; description: "~/Desktop" }
    }
    ListModel {
        id: runner
        ListElement { display: "Spark Calc"; decoration: "accessories-calculator"; description: "Calculator" }
        ListElement { display: "Display Configuration"; decoration: "preferences-desktop-display"; description: "System Settings" }
    }

    Launcher {
        id: launcher
        anchors.fill: parent
        lang: "en"
        motion: false
        favoritesModel: pinned
        categoriesModel: categories
        categoryModelFor: row => row === 1 ? games : allApps
        allAppsModel: allApps
        recentModel: recent
        isPinned: id => id.indexOf("Soot") >= 0
        // main.qml handles this signal on its instance too; the launcher must still search
        property string lastQuery
        onQueryChanged: lastQuery = query
    }

    SignalSpy { id: activated; target: launcher; signalName: "activate" }
    SignalSpy { id: sums; target: launcher; signalName: "sumRequested" }
    SignalSpy { id: power; target: launcher; signalName: "powerRequested" }
    SignalSpy { id: closed; target: launcher; signalName: "closeRequested" }

    TestCase {
        name: "Launcher"
        when: windowShown

        function init() {
            launcher.opened();
            launcher.runnerModel = null;
            launcher.sumAnswer = "";
            launcher.sumAsked = "";
            launcher.lang = "en";
            activated.clear(); sums.clear(); power.clear(); closed.clear();
            tryVerify(() => launcher.apps.length === allApps.count);
        }

        function type(text) {
            for (let i = 0; i < text.length; i++) {
                keyClick(text[i]);
            }
        }

        function kinds() { return launcher.results.map(r => r.kind + ":" + r.name); }

        function save(item, name) {
            const done = item.grabToImage(result => result.saveToFile(window.shots + "/" + name + ".png"));
            verify(done);
            wait(50);
        }

        function test_0_screenshot_home() {
            waitForRendering(launcher);
            save(launcher, "launcher-home");
        }

        function test_search_box_filters_the_apps() {
            type("spark m");
            compare(launcher.query, "spark m");
            compare(launcher.lastQuery, "spark m");
            compare(kinds(), ["heading:APPS", "app:Spark Media", "app:Spark Monitor"]);
            verify(!findChild(launcher, "pinnedGrid").visible, "pinned apps hide while searching");
            keyClick(Qt.Key_Down);
            keyClick(Qt.Key_Return);
            compare(activated.count, 1);
            compare(activated.signalArguments[0][0], allApps);
            compare(activated.signalArguments[0][1], 6);   // Spark Monitor's row
        }

        function test_enter_opens_the_best_match() {
            type("calc");
            compare(launcher.results[1].name, "Spark Calc");
            keyClick(Qt.Key_Return);
            compare(activated.count, 1);
            compare(activated.signalArguments[0][1], 2);
        }

        function test_krunner_results_follow_without_repeats() {
            launcher.runnerModel = runner;
            type("cal");
            tryVerify(() => kinds().indexOf("runner:Display Configuration") > 0);
            compare(kinds().filter(k => k.endsWith("Spark Calc")).length, 1);
            verify(kinds().indexOf("heading:SETTINGS, FILES AND MORE") > 0);
            waitForRendering(launcher);
            save(launcher, "launcher-search");
        }

        function test_nothing_found() {
            type("qqqq");
            compare(launcher.results.length, 0);
            keyClick(Qt.Key_Escape);
            compare(launcher.query, "");
            keyClick(Qt.Key_Escape);
            compare(closed.count, 1);
        }

        function test_sum_goes_to_spark_calc() {
            type("0.1+0.2");
            tryCompare(sums, "count", 1);
            compare(sums.signalArguments[0][0], "0.1+0.2");
            launcher.sumAsked = "0.1+0.2";
            launcher.sumAnswer = "0.3";
            compare(launcher.results[0].kind, "sum");
            compare(launcher.results[0].name, "= 0.3");
            keyClick(Qt.Key_Return);
            verify(launcher.copied);
            compare(activated.count, 0);
            waitForRendering(launcher);
            save(launcher, "launcher-sum");
        }

        function test_words_are_not_sums() {
            type("firefox");
            wait(200);
            compare(sums.count, 0);
        }

        function test_shut_down_asks_first() {
            mouseClick(findChild(launcher, "shutdownButton"));
            compare(launcher.confirming, "shutdown");
            compare(power.count, 0);
            waitForRendering(launcher);
            save(launcher, "launcher-confirm");
            mouseClick(findChild(launcher, "cancelButton"));
            compare(launcher.confirming, "");
            compare(power.count, 0);
            mouseClick(findChild(launcher, "restartButton"));
            mouseClick(findChild(launcher, "confirmButton"));
            compare(power.count, 1);
            compare(power.signalArguments[0][0], "restart");
        }

        function test_lock_needs_no_question() {
            mouseClick(findChild(launcher, "lockButton"));
            compare(power.count, 1);
            compare(power.signalArguments[0][0], "lock");
        }

        function test_categories_switch_the_list() {
            const list = findChild(launcher, "appList");
            compare(list.count, allApps.count);
            launcher.category = 1;
            compare(list.count, 1);
        }

        function test_store_link_opens_spark_store() {
            verify(launcher.store !== null);
            compare(launcher.store.row, 7);
        }

        function test_french() {
            launcher.lang = "fr";
            type("zzz");
            compare(launcher.t("nothing", "zzz"), "Rien trouvé pour « zzz ».");
            keyClick(Qt.Key_Escape);
            waitForRendering(launcher);
            save(launcher, "launcher-home-fr");
        }
    }
}
