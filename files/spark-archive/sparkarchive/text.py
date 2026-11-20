"""Every sentence the interface shows, in one place, so a French translation can be added as
a second table. t('key', name=...) fills in the blanks."""

from .core import languages

EN = {
    # window
    'empty.title': "No archive open",
    'empty.body': "Open a zip, tar, 7z, rar or iso file to see what's inside. In Dolphin, "
                  "right-click an archive for Extract here, or any files for Compress.",
    'button.open': "Open archive",
    'button.compress': "Compress files",
    'button.extract_all': "Extract all",
    'button.extract_selected': "Extract selected",
    'button.extract_to': "Extract to…",
    'button.cancel': "Cancel",
    'button.close': "Close",
    'button.show': "Show in folder",
    'button.ok': "OK",
    'button.replace': "Replace",
    'button.skip': "Skip",
    'button.keep_both': "Keep both",
    'col.name': "Name",
    'col.size': "Size",
    'col.modified': "Modified",
    'chip.password': "PASSWORD",
    'summary': "{files} files · {size} unpacked · {fmt}",
    'summary.read_with': "read with {backend}",
    'selected': "{n} selected",

    # status words (the coloured dot line)
    'status.ready': "READY",
    'status.reading': "READING",
    'status.extracting': "EXTRACTING",
    'status.compressing': "COMPRESSING",
    'status.done': "DONE",
    'status.cancelled': "CANCELLED",
    'status.error': "ERROR",

    # progress
    'progress.reading': "Reading {name}…",
    'progress.files': "{done} of {total} files",
    'progress.bytes': "{done} of {total}",
    'progress.extract_title': "Extracting {name}",
    'progress.compress_title': "Compressing to {name}",
    'progress.cancelling': "Cancelling…",

    # compress choice in the window
    'compress.as': "Compress {n} items as",

    # password
    'password.title': "Password",
    'password.body': "{archive} is protected by a password.",
    'password.retry': "That password didn't work for {archive}. Try again.",
    'password.show': "show",

    # overwrite
    'overwrite.title': "Already there",
    'overwrite.body': "{name} already exists in this folder.",
    'overwrite.link': "{name} already exists in this folder (a link).",
    'overwrite.existing': "Existing:  {size}, {when}",
    'overwrite.new': "From archive:  {size}, {when}",
    'overwrite.all': "Do this for every file",

    # results
    'done.extracted': "Extracted {files} files to {folder}.",
    'done.extracted_selected': "Extracted {files} files to {folder}.",
    'done.compressed': "Made {name} ({size}).",
    'done.replaced': "{n} existing files replaced.",
    'done.skipped': "{n} files skipped (you chose Skip).",
    'done.problems': "Left out ({n}):",
    'done.cancelled_extract': "Cancelled. What this extraction had written was removed.",
    'done.cancelled_extract_replaced': "Cancelled. What this extraction had written was "
                                       "removed; {n} files it had already replaced stay "
                                       "replaced.",
    'done.cancelled_compress': "Cancelled. No archive was made.",

    # why something was left out
    'why.outside': "its path leads outside the folder",
    'why.link_out': "a link that points outside the folder",
    'why.special': "a device, pipe or socket",
    'why.refused': "the 7z command refused it as unsafe",
    'why.in_the_way': "a folder or link with that name is in the way",
    'why.failed': "the system refused: {why}",
    'why.unreadable': "couldn't read it: {why}",

    # errors
    'error.missing': "The file isn't there any more.",
    'error.not_archive': "This isn't an archive Spark Archive can read (zip, tar, 7z, rar, "
                         "iso, gz, bz2, xz or zst).",
    'error.unsupported': "Spark Archive can't read this archive: {detail}",
    'error.password': "This archive needs a password.",
    'error.damaged': "This archive is damaged or incomplete: {detail}",
    'error.read_failed': "Couldn't read the archive: {detail}",
    'error.no_folder': "The folder {detail} isn't there.",
    'error.cant_write': "Can't write there: {detail}",
    'error.no_space': "Not enough free space on the disk.",
    'error.write_failed': "Writing failed: {detail}",
    'error.nothing': "There was nothing to compress.",
    'error.bug': "Something went wrong inside Spark Archive: {detail}. It's in the log.",
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
    try:
        return text.format(**kw) if kw else text
    except (KeyError, IndexError, ValueError):
        return text


def why(reason: str) -> str:
    """'failed:Permission denied' -> 'the system refused: Permission denied'"""
    key, _, detail = reason.partition(':')
    return t('why.' + key, why=detail) if detail else t('why.' + key)
