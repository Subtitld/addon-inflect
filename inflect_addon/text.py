"""Inflect v2's English text frontend: normalization, phonemes, token ids.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

Ported from upstream's `inflect_nano_v2_frontend.py`, `inflect_vits_frontend.py`
and `onnx/inference_onnx.py` (Copyright Owen Song, Apache-2.0), and the symbol
table `runtime/text/symbols.py` (from keithito/tacotron, Copyright (c) 2017
Keith Ito, MIT). The normalization is upstream's, rule for rule: the model
learned to read its output, so it is not "improved" here. Phonemization goes
through espeak.py instead of the phonemizer package.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import numpy as np
from num2words import num2words

log = logging.getLogger('inflect_addon.text')

# ---------------------------------------------------------------------------
# Symbols (runtime/text/symbols.py)
# ---------------------------------------------------------------------------
_PAD = '_'
_PUNCTUATION = ';:,.!?¡¿—…"«»“” '
_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
_LETTERS_IPA = ("ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶʘɹɺɾɻʀʁɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑʼʴʰʱʲʷˠˤ˞↓↑→↗↘'̩'ᵻ")
SYMBOLS = [_PAD] + list(_PUNCTUATION) + list(_LETTERS) + list(_LETTERS_IPA)
SYMBOL_TO_ID = {symbol: index for index, symbol in enumerate(SYMBOLS)}

# ---------------------------------------------------------------------------
# Normalization (inflect_nano_v2_frontend.py)
# ---------------------------------------------------------------------------
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
          'October', 'November', 'December']

WORD_OVERRIDES = {
    'Qwen3': 'Qwen three',
    'Qwen': 'Qwen',
    'PyTorch': 'pie torch',
    'SQLite': 'ess cue lite',
    'USB-C': 'you ess bee see',
    'RTX 3060': 'ar tee ex thirty sixty',
    'RTX 3090': 'ar tee ex thirty ninety',
    'RTX 4090': 'ar tee ex forty ninety',
    'RTX 5080': 'ar tee ex fifty eighty',
    'RTX 5090': 'ar tee ex fifty ninety',
}

LETTER_NAMES = {
    'A': 'ay', 'B': 'bee', 'C': 'see', 'D': 'dee', 'E': 'ee', 'F': 'eff', 'G': 'gee', 'H': 'aitch',
    'I': 'eye', 'J': 'jay', 'K': 'kay', 'L': 'ell', 'M': 'em', 'N': 'en', 'O': 'oh', 'P': 'pee',
    'Q': 'cue', 'R': 'ar', 'S': 'ess', 'T': 'tee', 'U': 'you', 'V': 'vee', 'W': 'double you',
    'X': 'ex', 'Y': 'why', 'Z': 'zee',
}

ABBREVIATIONS = {
    'Dr.': 'doctor',
    'Mr.': 'mister',
    'Mrs.': 'missus',
    'Ms.': 'miss',
    'Prof.': 'professor',
    'St.': 'saint',
    'vs.': 'versus',
    'etc.': 'et cetera',
    'e.g.': 'for example',
    'i.e.': 'that is',
}

PUNCT_TRANSLATION = str.maketrans({
    '‘': "'",
    '’': "'",
    '“': '"',
    '”': '"',
    '–': '-',
    '—': ', ',
    '…': '...',
    '(': ', ',
    ')': ', ',
    '[': ', ',
    ']': ', ',
    '{': ', ',
    '}': ', ',
})


def _words(value: int | float, *, ordinal: bool = False) -> str:
    text = num2words(value, to='ordinal') if ordinal else num2words(value)
    return text.replace('-', ' ').replace(',', '')


def _digit_words(text: str) -> str:
    return ' '.join(_words(int(ch)) for ch in text if ch.isdigit())


def _identifier_digits(text: str) -> str:
    words = []
    for index, character in enumerate(text):
        if not character.isdigit():
            continue
        words.append('oh' if character == '0' and index > 0 else _words(int(character)))
    return ' '.join(words)


def _expand_identifier_token(token: str) -> str:
    match = re.fullmatch(r'([A-Za-z]?)(\d+)([A-Za-z]?)', token)
    if match is None:
        return token
    prefix, digits, suffix = match.groups()
    pieces = []
    if prefix:
        pieces.append(LETTER_NAMES[prefix.upper()])
    if len(digits) == 3 or digits.startswith('0'):
        pieces.append(_identifier_digits(digits))
    else:
        pieces.append(_words(int(digits)))
    if suffix:
        pieces.append(LETTER_NAMES[suffix.upper()])
    return ' '.join(pieces)


def _expand_labeled_identifier(match: re.Match) -> str:
    return f'{match.group(1)} {_expand_identifier_token(match.group(2))}'


def _expand_street_number(match: re.Match) -> str:
    return _identifier_digits(match.group(1))


def _expand_money(match: re.Match) -> str:
    raw = match.group(1).replace(',', '')
    dollars, _, cents = raw.partition('.')
    dollar_count = int(dollars)
    parts = [_words(dollar_count), 'dollar' if dollar_count == 1 else 'dollars']
    if cents:
        cents = cents[:2].ljust(2, '0')
        cent_count = int(cents)
        if cent_count:
            parts.extend(['and', _words(cent_count), 'cent' if cent_count == 1 else 'cents'])
    return ' '.join(parts)


def _expand_date_slash(match: re.Match) -> str:
    month = int(match.group(1))
    day = int(match.group(2))
    year = int(match.group(3))
    try:
        date(year, month, day)
    except ValueError:
        return match.group(0)
    return f'{MONTHS[month - 1]} {_words(day, ordinal=True)} {_words(year)}'


def _expand_time(match: re.Match) -> str:
    hour = int(match.group(1))
    minute = int(match.group(2))
    suffix = match.group(3) or ''
    pieces = [_words(hour)]
    if minute == 0:
        pieces.append('o clock')
    elif minute < 10:
        pieces.extend(['oh', _words(minute)])
    else:
        pieces.append(_words(minute))
    if suffix:
        suffix = suffix.lower().replace('.', '')
        pieces.extend(list(suffix))
    return ' '.join(pieces)


def _expand_bare_hour_time(match: re.Match) -> str:
    hour = int(match.group(1))
    suffix = re.sub(r'[^A-Za-z]', '', match.group(2)).lower()
    return f"{_words(hour)} {' '.join(suffix)}"


def _expand_version(match: re.Match) -> str:
    return ' point '.join(_words(int(part)) for part in match.group(0).split('.'))


def _expand_decimal(match: re.Match) -> str:
    whole, frac = match.group(1), match.group(2)
    return f'{_words(int(whole))} point {_digit_words(frac)}'


def _expand_ordinal(match: re.Match) -> str:
    return _words(int(match.group(1)), ordinal=True)


def _expand_number(match: re.Match) -> str:
    value = match.group(0).replace(',', '')
    if len(value) >= 5 and not value.startswith('20'):
        return _digit_words(value)
    return _words(int(value))


def _expand_phone(match: re.Match) -> str:
    left, right = match.group(1), match.group(2)
    return f'{_digit_words(left)}, {_digit_words(right)}'


def _expand_acronym(match: re.Match) -> str:
    acronym = match.group(0)
    if len(acronym) <= 1:
        return acronym
    return ' '.join(LETTER_NAMES.get(ch, ch) for ch in acronym)


def normalize_text(text: str) -> str:
    text = text.translate(PUNCT_TRANSLATION)
    text = re.sub(r'\s+', ' ', text).strip()

    for src, dst in WORD_OVERRIDES.items():
        text = re.sub(rf'\b{re.escape(src)}\b', dst, text)
    for src, dst in ABBREVIATIONS.items():
        text = re.sub(rf'\b{re.escape(src)}', dst, text, flags=re.IGNORECASE)

    text = re.sub(r'\b([A-Z])(?:\.([A-Z]))+\.', lambda m: ' '.join(re.findall(r'[A-Z]', m.group(0))), text)
    text = re.sub(
        r'\b(apartment|apt\.?|suite|unit|room|flight|extension|order|invoice|locker|aisle|gate)'
        r'\s+([A-Za-z]?\d{1,4}[A-Za-z]?)\b',
        _expand_labeled_identifier,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\b(\d{3})(?=\s+(?:North|South|East|West)\b)', _expand_street_number, text,
                  flags=re.IGNORECASE)
    text = re.sub(r'\$(\d[\d,]*(?:\.\d{1,2})?)', _expand_money, text)
    text = re.sub(r'\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/(20\d{2}|19\d{2})\b', _expand_date_slash, text)
    text = re.sub(r'\b(\d{1,2}):(\d{2})\s*([AaPp]\.?\s*[Mm]\.?)?\b', _expand_time, text)
    text = re.sub(r'\b(\d{1,2})\s*([AaPp]\.?\s*[Mm]\.?)\b', _expand_bare_hour_time, text)
    text = re.sub(r'\b(\d{3})-(\d{4})\b', _expand_phone, text)
    text = re.sub(r'\b\d+(?:\.\d+){2,}\b', _expand_version, text)
    text = re.sub(r'\b(\d+)\.(\d+)\b', _expand_decimal, text)
    text = re.sub(r'\b(\d+)(st|nd|rd|th)\b', _expand_ordinal, text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d[\d,]*\b', _expand_number, text)
    text = re.sub(r'\b[A-Z]{2,}\b', _expand_acronym, text)
    text = re.sub(r',(?:\s*,)+', ',', text)
    text = re.sub(r',\s*([.!?])', r'\1', text)
    text = re.sub(r'\s+([,;:.!?])', r'\1', text)
    text = re.sub(r'([,;:.!?])(?=\S)', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()


# ---------------------------------------------------------------------------
# Phonemes (inflect_vits_frontend.py)
# ---------------------------------------------------------------------------
# Upstream's verified exceptions to espeak.
PHONEME_OVERRIDES = {
    'sˈæskɐtʃˌuːən': 'sɐskˈætʃəwən',
    'flʊɹɹˈɛsənt': 'flʊˈɹɛsənt',
}


def apply_phoneme_overrides(phoneme_text: str) -> str:
    for source, replacement in PHONEME_OVERRIDES.items():
        phoneme_text = phoneme_text.replace(source, replacement)
    return re.sub(r'\s+', ' ', phoneme_text).strip()


def phonemize(espeak, normalized_text: str) -> str:
    """The model's phoneme string for already normalized text."""
    from inflect_addon.espeak import strip_language_flags

    phonemes = espeak.phonemize(normalized_text)
    # Upstream keeps espeak's language switch flags ("(fr)") and then fails on
    # their letters; speak the word in espeak's foreign phonemes instead.
    phonemes, switched = strip_language_flags(phonemes)
    if switched:
        log.info('espeak switched language inside %r', normalized_text[:80])
    return apply_phoneme_overrides(phonemes)


def tokens(phoneme_text: str) -> np.ndarray:
    """Token ids with a blank (0) between and around them, shape (1, 2n + 1).

    A character outside the symbol table is dropped, where upstream would
    fail the whole line on it.
    """
    sequence = [SYMBOL_TO_ID[symbol] for symbol in phoneme_text if symbol in SYMBOL_TO_ID]
    dropped = {symbol for symbol in phoneme_text if symbol not in SYMBOL_TO_ID}
    if dropped:
        log.info('dropped symbols the model does not know: %s', ' '.join(sorted(dropped)))
    if not sequence:
        raise ValueError('The text frontend produced no speakable tokens.')
    with_blanks = np.zeros(len(sequence) * 2 + 1, dtype=np.int64)
    with_blanks[1::2] = sequence
    return with_blanks[None, :]
