"""Every sentence the interface shows, in one place, so a French table can be added next to
the English one. t('key', name=...) fills in the blanks."""

from .core import languages

EN = {
    # header and tabs
    'untitled': "Untitled",
    'untitled_n': "Untitled {n}",
    'tip.new': "New (Ctrl+N)",
    'tip.open': "Open (Ctrl+O)",
    'tip.save': "Save (Ctrl+S)",
    'tip.find': "Find (Ctrl+F)",
    'tip.menu': "Menu",

    # menu
    'menu.new': "New",
    'menu.open': "Open…",
    'menu.recent': "Open recent",
    'menu.recent_empty': "Nothing yet",
    'menu.recent_clear': "Clear the list",
    'menu.save': "Save",
    'menu.save_as': "Save as…",
    'menu.save_admin': "Save as administrator…",
    'menu.reload': "Reload from disk",
    'menu.close': "Close tab",
    'menu.close_others': "Close other tabs",
    'menu.reopen_closed': "Reopen closed tab",
    'menu.copy_path': "Copy path",
    'menu.find': "Find",
    'menu.replace': "Replace",
    'menu.goto': "Go to line",
    'menu.comment': "Comment or uncomment lines",
    'menu.wrap': "Word wrap",
    'menu.zoom_in': "Zoom in",
    'menu.zoom_out': "Zoom out",
    'menu.zoom_reset': "Actual size",
    'menu.session': "Reopen last session at start",
    'menu.quit': "Quit",
    'menu.reopen_with': "Reopen with",
    'menu.save_with': "Save with",
    'menu.plain': "Plain text",

    # start screen
    'start.title': "Nothing open",
    'start.new': "New file",
    'start.open': "Open file",
    'start.recent': "Recent",
    'start.no_recent': "Files you open show up here.",

    # find bar
    'find.find': "Find",
    'find.replace': "Replace",
    'find.replace_one': "Replace",
    'find.replace_all': "Replace all",
    'find.case': "Case",
    'find.word': "Word",
    'find.regex': "Regex",
    'find.count': "{i} of {n}",
    'find.count_many': "{i} of {n}+",
    'find.none': "No matches",
    'find.bad': "Bad pattern: {why}",
    'find.replaced': "Replaced {n}.",
    'find.goto': "Go to line",
    'find.goto_hint': "line, or line:column (1-{n})",
    'find.loading': "Wait until the file has loaded",
    'find.enter': "Big file: press Enter to search",

    # status bar
    'status.position': "Ln {line}, Col {col}",
    'status.selected': "{n} selected",
    'status.wrap': "Wrap",
    'status.nowrap': "No wrap",
    'status.loading': "Loading {pct}%",
    'status.opening': "Opening {name}…",
    'status.saved': "Saved {path}",
    'status.saved_admin': "Saved {path} as administrator",
    'status.new_file': "New file: {path} is created when you save",
    'status.reloaded': "Reloaded {name}: it changed on disk",
    'status.read_only': "Read-only for you",
    'status.read_only_fs': "Read-only file system",
    'status.restored': "Brought back {n} unsaved file(s) from last time",
    'status.restored_changed': "{name} changed on disk since your unsaved edits; saving "
                               "overwrites it",
    'status.big': "{name} is {size}: word wrap is off for it",
    'status.mixed': "{name} mixed line endings; it will be saved with {nl}",
    'status.encoding_set': "{name} will be saved as {enc}",
    'status.newline_set': "{name} will be saved with {nl} line endings",
    'status.no_comment': "{lang} has no line comments",
    'status.admin_wait': "Waiting for the password…",
    'status.copied': "Copied the path",

    # dialogs
    'button.save': "Save",
    'button.dont_save': "Don't save",
    'button.cancel': "Cancel",
    'button.open_anyway': "Open anyway",
    'button.overwrite': "Overwrite",
    'button.reload': "Reload",
    'button.keep': "Keep mine",
    'button.admin': "Save as administrator",
    'button.save_as': "Save as…",
    'button.utf8': "Save as UTF-8",
    'button.ok': "OK",
    'ask.unsaved_title': "Save changes?",
    'ask.unsaved': "{name} has changes that aren't saved.",
    'ask.binary_title': "Not a text file",
    'ask.binary': "{name} looks like a binary file (it has NUL bytes). Opening it as text "
                  "shows mostly noise, and saving it can damage it.",
    'ask.changed_title': "Changed on disk",
    'ask.changed': "{name} was changed by another program since you opened it.\n\n"
                   "Save anyway and overwrite those changes?",
    'ask.changed_reload': "{name} was changed by another program, and you have unsaved "
                          "edits here.\n\nReload it from disk and lose your edits?",
    'ask.denied_title': "You can't write this file",
    'ask.denied': "{path} belongs to the system or another user.\n\nSave as administrator "
                  "asks for your password and writes it with root rights.",
    'ask.denied_no_pkexec': "{path} belongs to the system or another user, and pkexec "
                            "isn't installed, so it can't be saved as administrator.",
    'ask.rofs_title': "Read-only file system",
    'ask.rofs': "{path} is on a read-only file system, so nobody can change it, not even "
                "the administrator. On SparkOS everything under /usr is part of the image; "
                "settings go in /etc or your home folder.\n\nSave a copy somewhere else?",
    'ask.encode_title': "Can't save in {enc}",
    'ask.encode': "Line {line}, column {col} has “{char}”, which {enc} can't hold.\n\n"
                  "Save the file as UTF-8 instead?",
    'ask.error_title': "Couldn't save",
    'ask.error': "{path}\n\n{why}",
    'ask.open_error_title': "Couldn't open",
    'ask.open_error': "{path}\n\n{why}",
    'ask.reopen_dirty_title': "Reopen with another encoding?",
    'ask.reopen_dirty': "Reopening {name} as {enc} loses the changes you haven't saved.",
    'ask.admin_failed': "Saving as administrator didn't work:\n\n{why}",
    'error.is_folder': "That's a folder, not a file",
    'error.cancelled': "Cancelled",
}

TABLES = {'en': EN}


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
