"""Every sentence Spark Update shows, in one place, so a French translation can be added as a
second table. t('key', name=...) fills in the blanks."""

import locale
import os

EN = {
    # the notification (the approved mockup)
    'notify.ready.title': "SparkOS updated",
    'notify.ready.body': "The new version is ready. It starts the next time you restart.",
    'notify.apps_ok': "Your apps are already up to date.",
    'notify.available.title': "SparkOS update available",
    'notify.available.body': "SparkOS {version} is ready to download. Open Spark Update to "
                             "get it.",
    'notify.available.body_no_version': "A new SparkOS version is ready to download. Open "
                                        "Spark Update to get it.",
    'notify.later': "Later",
    'notify.restart': "Restart",
    'notify.open': "Open",

    # status line under the title
    'status.reading': "READING",
    'status.up_to_date': "UP TO DATE",
    'status.ready': "UPDATE READY · RESTART TO USE IT",
    'status.available': "UPDATE AVAILABLE",
    'status.checking': "CHECKING",
    'status.downloading': "DOWNLOADING",
    'status.flatpak': "UPDATING APPS",
    'status.failed': "LAST CHECK FAILED",
    'status.rolled_back': "PREVIOUS VERSION AT NEXT RESTART",
    'status.no_image': "NOT RUNNING FROM AN IMAGE",
    'status.test_data': "TEST DATA",

    # panels
    'panel.this_pc': "This PC runs",
    'panel.next': "Next restart",
    'panel.changes_update': "What the update changes",
    'panel.changes_current': "What changed in this version",
    'panel.changes_rollback': "What rolling back changes",
    'panel.contents': "What's in this version",
    'panel.apps': "Apps (Flatpak)",
    'panel.checks': "Checks",

    'pc.version': "SparkOS {version}",
    'pc.built': "built {date}",
    'pc.image': "{image}",
    'pc.unknown': "Can't read the system status: {why}",
    'next.same': "The same version. Nothing waits for a restart.",
    'next.staged': "SparkOS {version}, downloaded and ready",
    'next.rollback': "SparkOS {version}, the previous version (you rolled back)",
    'next.pinned': "pinned",

    'changes.since': "Compared with {version}, the version before it on this PC.",
    'changes.update': "Compared with the version running now.",
    'changes.none': "Same versions of SparkOS's apps and drivers.",
    'changes.same': "{n} more unchanged",
    'changes.added': "new",
    'changes.removed': "removed",
    'changes.no_list': "{version} was built before SparkOS listed what's inside each version, "
                       "and its files can't be read here, so there's nothing to compare.",
    'changes.unreadable': "Can't read the files of {version} on this PC.",
    'changes.no_previous': "There's no earlier version on this PC to compare with.",
    'changes.from_files': "read from the version's files",

    'apps.updated': "{n} updated {when}: {names}",
    'apps.none': "Up to date (checked {when}).",
    'apps.failed': "Couldn't update {when}: {why}",
    'apps.off': "Flatpak updates are off.",
    'apps.not_yet': "Not updated by Spark Update yet.",
    'apps.yours': "Yours",
    'apps.system': "System",

    # while Universal Blue's uupd does the downloading (engine.py)
    'uupd.failed': "uupd's last run failed; the Log shows why.",
    'apps.uupd_ok': "Updated by uupd together with SparkOS ({when}).",
    'apps.uupd_failed': "uupd's last run ({when}) didn't finish; your apps may not be up to "
                        "date.",
    'apps.uupd_never': "Updated by uupd together with SparkOS; it hasn't run yet.",
    'check.uupd': "Universal Blue's uupd downloads updates for now: daily around 04:00, and "
                  "when you click Check now.",
    'check.uupd_running': "It's running now.",
    'check.uupd_failed': "Its last run ({when}) failed; see the Log.",
    'set.uupd': "Universal Blue's uupd downloads updates for now, daily around 04:00; these "
                "settings apply once Spark Update does it itself.",
    'log.uupd': "uupd (downloads updates for now)",

    'check.last': "Last check {when}.",
    'check.never': "Not checked yet.",
    'check.next': "Next check after {when}.",
    'check.off': "Automatic updates are off: it checks only when you click Check now.",
    'check.notify_only': "Notify only: it checks and tells you, and downloads nothing until "
                         "you click.",
    'check.postponed': "Waiting for a later hour: {why}.",
    'check.failed': "The last check failed: {why}",
    'check.direct': "Background checks come with the SparkOS image; this copy checks only "
                    "when you click.",

    # buttons
    'btn.check': "Check now",
    'btn.download': "Download update",
    'btn.restart': "Restart to update",
    'btn.restart_plain': "Restart",
    'btn.rollback': "Roll back",
    'btn.undo_rollback': "Cancel roll back",
    'btn.settings': "Settings",
    'btn.log': "Log",
    'btn.back': "Back",
    'btn.save': "Save",
    'btn.cancel': "Cancel",

    # messages
    'msg.checking': "Checking for a new SparkOS version...",
    'msg.check_started': "Checking. You can close this window; it carries on.",
    'msg.check_failed': "Couldn't start the check: {why}",
    'msg.up_to_date': "SparkOS is up to date.",
    'msg.staged': "SparkOS {version} is ready. It starts the next time you restart.",
    'msg.available': "SparkOS {version} is available.",
    'msg.failed': "The check failed: {why}",
    'msg.rolled_back': "The next restart starts SparkOS {version}. Nothing was deleted.",
    'msg.unrolled': "Roll back cancelled: the next restart starts the version running now.",
    'msg.rollback_failed': "Couldn't roll back: {why}",
    'msg.cancelled': "Cancelled: nothing changed.",
    'msg.saved': "Saved.",
    'msg.save_failed': "Couldn't save: {why}",
    'msg.restart_failed': "Couldn't restart. Restart from the menu instead.",
    'msg.test_data': "Not done: Spark Update is showing test data, not this PC.",

    # roll back dialog
    'rollback.title': "Roll back to the previous version?",
    'rollback.body': "The next time you restart, your PC starts SparkOS {old} (from {date}) "
                     "instead of {current}.\n\nNothing is deleted: your files, settings and "
                     "apps stay as they are, and {current} stays on the PC, so you can come "
                     "back to it with Cancel roll back.\n\nAutomatic updates will download "
                     "the newest version again later; turn them off in Settings if you want "
                     "to stay on {old}.",
    'rollback.go': "Roll back",
    'rollback.restart_now': "Rolled back. Restart now to start SparkOS {version}?",
    'rollback.later': "Not now",
    'restart.title': "Restart now?",
    'restart.body': "Your apps are asked to close first; any that have unsaved work can stop "
                    "the restart.",

    # settings
    'set.system': "For everyone on this PC",
    'set.automatic': "Automatic updates",
    'set.automatic_note': "Check on its own, a few times a day. Never while a game runs, on "
                          "a metered connection or a low battery.",
    'set.every': "Check every",
    'set.hours': "{n} h",
    'set.mode': "When there's an update",
    'set.mode.stage': "Download it",
    'set.mode.notify': "Only tell me",
    'set.flatpak': "Update Flatpak apps too",
    'set.user': "Just for you",
    'set.notify': "Notify me when an update is ready",
    'set.remind': "After Later, remind me",
    'set.remind.24': "Next day",
    'set.remind.72': "In 3 days",
    'set.remind.168': "In a week",
    'set.admin_note': "Saving these asks for an administrator password.",
    'set.no_helper': "These come with the SparkOS image install; this copy can't change them.",
    'set.conf_warnings': "update.conf has lines it ignored: {lines}",

    'log.system': "Background checks",
    'log.user': "This account",
    'log.empty': "Nothing logged yet.",
}

TABLES = {'en': EN}


def languages():
    lang = os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


def _table():
    for lang in languages():
        short = lang.split('_')[0].lower()
        if short in TABLES:
            return TABLES[short]
    return EN


_T = _table()


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
