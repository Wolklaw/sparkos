#!/usr/bin/env python3
"""Build Spark Emoji's data files from the Unicode Consortium's own data.

    python3 tools/make_data.py --fetch DIR      download the sources into DIR
    python3 tools/make_data.py --sources DIR    write sparkemoji/data/emoji.json and symbols.json

Sources (licence Unicode-3.0, a permissive licence; see THIRD-PARTY.md):
  emoji-test.txt                          unicode.org/Public/emoji/latest/
  common/annotations/{en,fr}.xml          CLDR, github.com/unicode-org/cldr
  common/annotationsDerived/{en,fr}.xml   CLDR

The generated files are committed, so building the image needs no network. Run this again
when a new Unicode version comes out.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'sparkemoji', 'data')

SOURCES = {
    'emoji-test.txt': 'https://unicode.org/Public/emoji/latest/emoji-test.txt',
    'en.xml': 'https://raw.githubusercontent.com/unicode-org/cldr/main/common/annotations/en.xml',
    'fr.xml': 'https://raw.githubusercontent.com/unicode-org/cldr/main/common/annotations/fr.xml',
    'enD.xml': 'https://raw.githubusercontent.com/unicode-org/cldr/main/common/annotationsDerived/en.xml',
    'frD.xml': 'https://raw.githubusercontent.com/unicode-org/cldr/main/common/annotationsDerived/fr.xml',
}

GROUPS = {
    'Smileys & Emotion': ('smileys', 'Smileys and emotion', 'Visages et émotions'),
    'People & Body': ('people', 'People and body', 'Personnes et corps'),
    'Animals & Nature': ('nature', 'Animals and nature', 'Animaux et nature'),
    'Food & Drink': ('food', 'Food and drink', 'Nourriture et boissons'),
    'Travel & Places': ('travel', 'Travel and places', 'Voyages et lieux'),
    'Activities': ('activities', 'Activities', 'Activités'),
    'Objects': ('objects', 'Objects', 'Objets'),
    'Symbols': ('symbols', 'Symbols', 'Symboles'),
    'Flags': ('flags', 'Flags', 'Drapeaux'),
}
TONES = ('\U0001F3FB', '\U0001F3FC', '\U0001F3FD', '\U0001F3FE', '\U0001F3FF')
TONE_RE = re.compile('[\U0001F3FB-\U0001F3FF]')


def strip_fe0f(s):
    return s.replace('️', '')


def read_annotations(*paths):
    """{cp without FE0F: (name, [keywords])} from CLDR annotation files; later files fill gaps."""
    out = {}
    for path in paths:
        names, words = {}, {}
        for node in ET.parse(path).getroot().iter('annotation'):
            cp = node.get('cp')
            if node.get('type') == 'tts':
                names[cp] = (node.text or '').strip()
            else:
                words[cp] = [w.strip() for w in (node.text or '').split('|') if w.strip()]
        for cp in set(names) | set(words):
            out.setdefault(cp, (names.get(cp, ''), words.get(cp, [])))
    return out


def build_emoji(src):
    en = read_annotations(os.path.join(src, 'en.xml'), os.path.join(src, 'enD.xml'))
    fr = read_annotations(os.path.join(src, 'fr.xml'), os.path.join(src, 'frD.xml'))
    group = None
    entries = []           # (group, chars, test-name)
    version = ''
    with open(os.path.join(src, 'emoji-test.txt'), encoding='utf-8') as f:
        for line in f:
            if line.startswith('# Version:'):
                version = line.split(':', 1)[1].strip()
            m = re.match(r'# group: (.+)', line)
            if m:
                group = m.group(1).strip()
                continue
            m = re.match(r'([0-9A-F ]+?)\s*;\s*fully-qualified\s*# \S+ E[\d.]+ (.+)', line)
            if m and group in GROUPS:
                chars = ''.join(chr(int(h, 16)) for h in m.group(1).split())
                entries.append((group, chars, m.group(2)))
    by_key = {strip_fe0f(c): c for _, c, _ in entries}
    variants = {}          # base char -> five tone forms ('' where there is none)
    kept = []
    for grp, chars, name in entries:
        found = TONE_RE.findall(chars)
        if found:
            if len(set(found)) == 1:        # one tone throughout; mixed couples are left out
                base = by_key.get(strip_fe0f(TONE_RE.sub('', chars)))
                if base:
                    variants.setdefault(base, [''] * 5)[TONES.index(found[0])] = chars
            continue
        kept.append((grp, chars, name))

    def lookup(table, chars, fallback):
        got = table.get(strip_fe0f(chars)) or table.get(chars)
        return got if got else (fallback, [])

    result = []
    for key, (gid, gen, gfr) in GROUPS.items():
        items = []
        for grp, chars, name in kept:
            if grp != key:
                continue
            n_en, k_en = lookup(en, chars, name)
            n_fr, k_fr = lookup(fr, chars, name)
            row = [chars, n_en or name, n_fr or n_en or name,
                   ' '.join(w for w in k_en if w != n_en),
                   ' '.join(w for w in k_fr if w != n_fr)]
            if chars in variants and all(variants[chars]):
                row.append(variants[chars])
            items.append(row)
        result.append({'id': gid, 'en': gen, 'fr': gfr, 'items': items})
    return {'source': f'Unicode emoji-test.txt {version}; CLDR annotations (Unicode-3.0)',
            'groups': result}


# ─── symbols ────────────────────────────────────────────────

ACCENTS = {  # combining mark: (English, French)
    '̀': ('grave', 'accent grave'), '́': ('acute', 'accent aigu'),
    '̂': ('circumflex', 'accent circonflexe'), '̃': ('tilde', 'tilde'),
    '̈': ('diaeresis', 'tréma'), '̊': ('ring', 'rond en chef'),
    '̧': ('cedilla', 'cédille'), '̌': ('caron', 'caron'),
}
LETTERS = ('àâäáãåæ' 'çćč' 'éèêë' 'îïíì' 'ñ' 'ôöóòõøœ' 'ùûüú' 'ÿý' 'ß' 'š' 'ž'
           'ÀÂÄÁÃÅÆ' 'ÇĆČ' 'ÉÈÊË' 'ÎÏÍÌ' 'Ñ' 'ÔÖÓÒÕØŒ' 'ÙÛÜÚ' 'ŸÝ' 'Š' 'Ž')
SPECIAL_LETTERS = {  # no accent to read off
    'æ': ('ae ligature', 'ae dans l’o (æ)'), 'Æ': ('capital ae ligature', 'ae majuscule (Æ)'),
    'œ': ('oe ligature', 'e dans l’o (œ)'), 'Œ': ('capital oe ligature', 'e dans l’o majuscule (Œ)'),
    'ø': ('o with stroke', 'o barré'), 'Ø': ('capital o with stroke', 'o majuscule barré'),
    'ß': ('sharp s', 'eszett'),
}

SYMBOLS = [  # (id, English, French, characters)
    ('arrows', 'Arrows', 'Flèches', '←↑→↓↔↕↖↗↘↙⇐⇑⇒⇓⇔⇕↩↪↺↻⟵⟶⟷➜➔➤⏎↵⇄⇆↦'),
    ('math', 'Math', 'Maths', '±×÷=≠≈≡≤≥<>∞√∛∑∏∫∂∆∇∈∉∩∪⊂⊃⊆⊇∧∨¬∀∃∴∵∝∅′″°‰‱µπΩ−∙·⁄'),
    ('numbers', 'Fractions and powers', 'Fractions et exposants',
     '¼½¾⅓⅔⅕⅖⅗⅘⅙⅛⅜⅝⅞⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼ⁿ₀₁₂₃₄₅₆₇₈₉₊₋₌'),
    ('currency', 'Currency', 'Monnaies', '$€£¥¢¤₿₹₩₽₺₪₫₴₱₦฿₡₲₵₸₼₾'),
    ('letters', 'Accented letters', 'Lettres accentuées', LETTERS),
    ('punctuation', 'Punctuation', 'Ponctuation',
     '«»“”„‘’‚‹›–—―…•·†‡§¶©®™¡¿‽⸮№℅¦|\\/~^¨´`˜ªº'),
    ('greek', 'Greek', 'Grec', 'αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ'),
    ('shapes', 'Shapes and marks', 'Formes et marques',
     '■□▪▫▲△▶▷▼▽◀◁◆◇○●◎◉★☆✓✔✗✘✕✖☐☑☒♠♣♥♦♤♧♡♢♪♫♬♭♮♯☀☁☂☃☎☏✂✉✎✐⌘⌥⇧⌃⌫⌦⎋'),
    ('box', 'Lines and boxes', 'Traits et cadres', '─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬░▒▓█▀▄▌▐'),
]

FR_FALLBACK = {
    '×': 'multiplié par', '÷': 'divisé par', '°': 'degré', 'µ': 'micro', '²': 'au carré',
    '³': 'au cube', '·': 'point médian', '•': 'puce', '…': 'points de suspension',
}


def accent_name(ch):
    """('capital e acute', 'e majuscule accent aigu') for É, read off its decomposition."""
    d = unicodedata.normalize('NFD', ch)
    if len(d) < 2 or d[1] not in ACCENTS:
        return None
    en, fr = ACCENTS[d[1]]
    cap = d[0].isupper()
    base = d[0].lower()
    return (f"{'capital ' if cap else ''}{base} {en}",
            f"{base} {'majuscule ' if cap else ''}{fr}")


def build_symbols(src):
    en = read_annotations(os.path.join(src, 'en.xml'), os.path.join(src, 'enD.xml'))
    fr = read_annotations(os.path.join(src, 'fr.xml'), os.path.join(src, 'frD.xml'))
    groups = []
    seen = set()
    for gid, gen, gfr, chars in SYMBOLS:
        items = []
        for ch in chars:
            if ch in seen:
                continue
            seen.add(ch)
            n_en, k_en = en.get(ch, ('', []))
            n_fr, k_fr = fr.get(ch, ('', []))
            if ch in SPECIAL_LETTERS:
                n_en, n_fr = SPECIAL_LETTERS[ch]
            elif accent_name(ch):
                n_en, n_fr = accent_name(ch)
                k_en = k_fr = [unicodedata.normalize('NFD', ch)[0], 'accent']
            if not n_en:
                try:
                    n_en = unicodedata.name(ch).lower()
                except ValueError:
                    continue
            if not n_fr:
                n_fr = FR_FALLBACK.get(ch) or n_en
            items.append([ch, n_en, n_fr, ' '.join(w for w in k_en if w != n_en),
                          ' '.join(w for w in k_fr if w != n_fr)])
        groups.append({'id': gid, 'en': gen, 'fr': gfr, 'items': items})
    return {'source': 'Unicode character names; CLDR annotations (Unicode-3.0)', 'groups': groups}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--fetch', metavar='DIR', help='download the sources into DIR')
    ap.add_argument('--sources', metavar='DIR', help='read the sources from DIR and write the data')
    args = ap.parse_args()
    if args.fetch:
        os.makedirs(args.fetch, exist_ok=True)
        for name, url in SOURCES.items():
            print('fetching', url)
            urllib.request.urlretrieve(url, os.path.join(args.fetch, name))
    if args.sources:
        os.makedirs(DATA, exist_ok=True)
        for name, data in (('emoji.json', build_emoji(args.sources)),
                           ('symbols.json', build_symbols(args.sources))):
            with open(os.path.join(DATA, name), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                f.write('\n')
            n = sum(len(g['items']) for g in data['groups'])
            print(f'wrote {name}: {n} items')
    if not (args.fetch or args.sources):
        ap.print_help()
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
