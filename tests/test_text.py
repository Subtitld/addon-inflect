"""The normalizer and the token ids, as upstream defines them.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np
import pytest

from inflect_addon import engine, text


@pytest.mark.parametrize('raw, expected', [
    ('Dr. Smith paid $3.50 at 10:30 AM.', 'doctor Smith paid three dollars and fifty cents at ten thirty a m.'),
    ('On 12/25/2025 the NASA team met.', 'On December twenty fifth two thousand and twenty five the en ay ess ay team met.'),
    ('Version 1.2.3 (beta) — done…', 'Version one point two point three, beta, done. . .'),  # upstream's quirks included
    ('Call 555-1234 or gate B12.', 'Call five five five, one two three four or gate bee twelve.'),
    ('The 21st of 100,000 runs', 'The twenty first of one zero zero zero zero zero runs'),
])
def test_normalization(raw, expected):
    assert text.normalize_text(raw) == expected


def test_symbol_table_is_upstreams():
    # runtime/text/symbols.py: pad, 16 punctuation marks, 52 letters, 109 IPA symbols.
    assert len(text.SYMBOLS) == 1 + 16 + 52 + 109
    assert text.SYMBOLS[0] == '_' and text.SYMBOL_TO_ID[' '] == 16
    assert text.SYMBOL_TO_ID['ə'] == text.SYMBOLS.index('ə')


def test_tokens_interleave_blanks():
    ids = text.tokens('hə')
    assert ids.dtype == np.int64 and ids.shape == (1, 5)
    assert ids[0].tolist() == [0, text.SYMBOL_TO_ID['h'], 0, text.SYMBOL_TO_ID['ə'], 0]


def test_unknown_symbols_are_dropped_not_fatal():
    assert text.tokens('kwˈɑːsɑ̃').shape == (1, 2 * 7 + 1)  # the combining tilde goes
    with pytest.raises(ValueError):
        text.tokens('̃')


def test_phoneme_overrides():
    assert text.apply_phoneme_overrides('ɪn  sˈæskɐtʃˌuːən ') == 'ɪn sɐskˈætʃəwən'


def test_long_text_splits_like_upstream():
    assert engine.split_text('One. Two? Three!') == ['One.', 'Two?', 'Three!']
    long = ', '.join(['word ' * 10] * 8)
    chunks = engine.split_text(long)
    assert all(len(c) <= 280 for c in chunks) and ' '.join(chunks).split() == long.split()
    assert engine.boundary_pause_seconds('Why?') == 0.28 and engine.boundary_pause_seconds('so') == 0.08
