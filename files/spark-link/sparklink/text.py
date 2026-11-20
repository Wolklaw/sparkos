"""Every sentence Spark Link shows, in one place, so a French translation can be added as a
second table. t('key', name=...) fills in the blanks."""

import locale
import os
from typing import List

EN = {
    # service: pairing
    'pair.too_many': "Pairing stopped: a phone typed the wrong code five times. Start again "
                     "to get a new code.",
    'pair.timeout': "Pairing stopped: nobody answered on this PC within 2 minutes.",
    'pair.declined': "You didn't pair with {name}.",
    'pair.done': "Paired with {name}.",
    'pair.nothing': "No phone is waiting to pair.",

    # service: events shown in the window
    'ev.connected': "{name} connected.",
    'ev.disconnected': "{name} disconnected.",
    'ev.unpaired': "Unpaired {name}.",
    'ev.unpaired_by_phone': "{name} unpaired itself from this PC.",
    'ev.link': "Opened a link from {name}.",
    'ev.sent': "Sent {file} to {name}.",
    'ev.received': "Saved {file} from {name} in Downloads.",
    'ev.rejected': "{name} didn't take {file}.",
    'ev.failed': "{file}: {why}",

    # service: transfers
    'xfer.lost': "the phone disconnected",
    'xfer.phone_check': "the phone says the file arrived damaged",
    'xfer.cancelled_by': "{name} stopped the transfer",
    'xfer.cancelled': "stopped",
    'xfer.broken': "the phone sent the file out of order",
    'xfer.disk': "couldn't write it: {why}",
    'xfer.check': "it arrived damaged (size or checksum wrong), so it wasn't kept",
    'xfer.no_answer': "the phone didn't answer",
    'send.not_file': "not a file, or over 16 GB",

    # service: notifications
    'offer.title': "{name} wants to send a file",
    'offer.body': "{file} ({size}). Open Spark Link to accept or decline.",
    'received.title': "File from {name}",
    'received.body': "{file} is in Downloads.",
    'notify.app_unknown': "Phone",
    'battery.low_title': "{name}: battery low",
    'battery.low': "{level} % left and not charging.",
    'ring.here_title': "Looking for this PC",
    'ring.here': "{name} is ringing this PC.",

    # service: errors returned to the window and command line
    'err.port': "Can't listen on port {port}: {why}. Another program may be using it.",
    'err.running': "Spark Link is already running in the background.",
    'err.no_device': "That phone isn't paired.",
    'err.no_offer': "That transfer is no longer waiting.",
    'err.not_connected': "No paired phone is connected right now.",
    'err.feature_off': "That's switched off on this PC or on {name}.",
    'err.bad_url': "Only http:// and https:// links can be sent.",
    'err.no_service': "Spark Link isn't running in the background.",

    # window
    'app.status.running': "RUNNING",
    'app.status.listening': "LISTENING ON PORT {port}",
    'app.status.idle': "IDLE: NO PHONE PAIRED",
    'app.status.stopped': "NOT RUNNING",
    'app.tab.devices': "Phones",
    'app.tab.pair': "Pair a phone",
    'app.tab.features': "Features",
    'app.start': "Start Spark Link",
    'app.stopped': "Spark Link runs in the background so your phone can reach this PC. It "
                   "isn't running now.",
    'app.starting': "Starting…",
    'app.start_failed': "Couldn't start the background service: {why}",

    'dev.none': "No phone is paired yet. Open Soot on your phone, go to Link to PC, and "
                "pair it from the Pair a phone tab here.",
    'dev.connected': "CONNECTED",
    'dev.offline': "NOT CONNECTED",
    'dev.last_seen': "last seen {when}",
    'dev.never': "never connected",
    'dev.battery': "battery {level} %",
    'dev.battery_charging': "battery {level} %, charging",
    'dev.key': "key {key}",
    'dev.send_files': "Send files",
    'dev.send_link': "Send a link",
    'dev.ring': "Ring",
    'dev.unpair': "Unpair",
    'dev.always_accept': "Accept files without asking",
    'dev.unpair_title': "Unpair {name}?",
    'dev.unpair_confirm': "{name} won't be able to reach this PC until you pair it again.",
    'dev.rung': "Ringing {name}. Tap the phone to stop it.",
    'dev.link_title': "Send a link to {name}",
    'dev.link_prompt': "Paste a web address (http:// or https://)",
    'dev.link_send': "Send",
    'dev.link_sent': "Link sent to {name}.",
    'dev.files_title': "Send files to {name}",
    'dev.files_sending': "Offered {n} file(s) to {name}. They're sent once the phone accepts.",
    'just_now': "just now",
    'minutes_ago': "{n} min ago",
    'hours_ago': "{n} h ago",
    'days_ago': "{n} days ago",

    'pair.intro': "Pairing lets one phone reach this PC. Open Soot on your phone, go to "
                  "Link to PC, and scan this code.",
    'pair.start': "Show a pairing code",
    'pair.stop': "Stop pairing",
    'pair.waiting': "WAITING FOR THE PHONE · CODE EXPIRES IN {left}",
    'pair.expired': "The code expired. Show a new one to pair.",
    'pair.no_camera': "No camera? Copy this link to the phone:",
    'pair.copy': "Copy link",
    'pair.copied': "Link copied.",
    'pair.typed': "Or type in Soot: address {address}, code {code}. Soot will show a key; "
                  "check it reads {key}.",
    'pair.request': "Pair with {name}?",
    'pair.request_key': "The phone's key is {key}.",
    'pair.yes': "Pair",
    'pair.no': "Don't pair",
    'pair.not_listening': "Spark Link can't listen for phones: {why}",
    'pair.no_address': "This PC has no local network address right now.",

    'feat.url': "Links",
    'feat.url_about': "Open links and tabs sent from your phone in Soot, and send links "
                      "back.",
    'feat.clipboard': "Shared clipboard",
    'feat.clipboard_about': "Text you copy on one device can be pasted on the other. Off "
                            "unless you switch it on: everything you copy goes to the phone.",
    'feat.files': "Files",
    'feat.files_about': "Receive files into Downloads and send files to the phone. You "
                        "confirm each one unless you said otherwise for a phone.",
    'feat.notify': "Phone notifications",
    'feat.notify_about': "Show your phone's notifications on this PC. The phone asks for "
                         "permission to read them.",
    'feat.battery': "Battery",
    'feat.battery_about': "Show the phone's battery here, and warn at 15 %.",
    'feat.ring': "Find my phone",
    'feat.ring_about': "Make the phone ring at full volume from this PC.",
    'feat.local_only': "Everything stays on your local network. Spark Link has no account and "
                       "uses no outside server.",

    'offer.in': "{name} wants to send {file} ({size}).",
    'offer.accept': "Accept",
    'offer.decline': "Decline",
    'xfer.in': "from {name}",
    'xfer.out': "to {name}",
    'xfer.state.waiting': "waiting for you",
    'xfer.state.offered': "waiting for the phone",
    'xfer.state.sending': "sending",
    'xfer.state.sent': "checking",
    'xfer.state.receiving': "receiving",
    'xfer.state.done': "done",
    'xfer.state.failed': "failed",
    'xfer.state.rejected': "declined",
    'xfer.state.cancelled': "stopped",
    'xfer.stop': "Stop",
}

TABLES = {'en': EN}


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']"""
    lang = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or \
        os.environ.get('LANG') or ''
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
