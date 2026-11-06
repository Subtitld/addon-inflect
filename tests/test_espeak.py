"""espeak.py against the phonemizer package, through upstream's own frontend.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

tests/fixtures/phonemes.json holds what upstream's frontend (phonemizer 3.6
and espeak-ng 1.52.0) makes of every prompt of upstream's modern400
evaluation set, plus punctuation and quoting cases. tools/make_fixtures.py
wrote it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from inflect_addon import espeak, text

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
PHONEMES = json.loads((FIXTURES / 'phonemes.json').read_text(encoding='utf-8'))
ENGLISH_DATA = ('phontab', 'phonindex', 'phondata', 'intonations', 'en_dict', 'lang/gmw/en-US')


def test_espeak_is_the_version_upstream_used(espeak_engine):
    assert espeak_engine.version == '1.52.0'


def test_phonemes_match_upstream_for_every_fixture(espeak_engine):
    assert len(PHONEMES) >= 400
    wrong = {}
    for raw, expected in PHONEMES.items():
        got = text.phonemize(espeak_engine, text.normalize_text(raw))
        if got != expected:
            wrong[raw] = (expected, got)
    assert not wrong, f'{len(wrong)} differ, e.g. {next(iter(wrong.items()))}'


@pytest.mark.parametrize('raw, expected', [
    ('Hello, world!', 'həlˈoʊ, wˈɜːld!'),
    ('He said "hi" twice.', 'hiː sˈɛd "hˈaɪ" twˈaɪs.'),
    ('', ''),
    ('...', '...'),
])
def test_punctuation_is_kept_in_place(espeak_engine, raw, expected):
    assert espeak_engine.phonemize(raw) == expected


def test_language_flags_are_dropped():
    assert espeak.strip_language_flags('ðə (fr)ʃɑːtˈoː(en) ɪz') == ('ðə ʃɑːtˈoː ɪz', True)
    assert espeak.strip_language_flags('nˈoʊ flˈæɡz') == ('nˈoʊ flˈæɡz', False)


def test_the_english_data_alone_phonemizes_the_same(tmp_path, espeak_engine):
    """The frozen build ships only these files (tools/stage_espeak.py)."""
    library, data = espeak.locate()
    subset = tmp_path / 'espeak-ng-data'
    for name in ENGLISH_DATA:
        (subset / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(data) / name, subset / name)
    sample = list(PHONEMES)[:60]
    # A second library instance would share the first one's global state, so
    # compare in a child process.
    import subprocess
    import sys
    code = ('import json, sys; from inflect_addon import espeak, text; '
            'e = espeak.Espeak(sys.argv[1], sys.argv[2]); '
            'print(json.dumps([text.phonemize(e, text.normalize_text(t)) for t in json.loads(sys.argv[3])]))')
    out = subprocess.run([sys.executable, '-c', code, str(library), str(subset), json.dumps(sample)],
                         capture_output=True, text=True, check=True,
                         env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])))
    assert json.loads(out.stdout) == [PHONEMES[t] for t in sample]


def test_a_data_path_too_long_for_espeak_is_copied(tmp_path):
    """espeak-ng truncates a data path over 160 bytes without saying so."""
    library, data = espeak.locate()
    deep = tmp_path / ('d' * 60) / ('e' * 60) / 'espeak-ng-data'
    for name in ENGLISH_DATA:
        (deep / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(data) / name, deep / name)
    import subprocess
    import sys
    code = ('import sys; from inflect_addon import espeak; e = espeak.Espeak(sys.argv[1], sys.argv[2]); '
            'print(e._scratch is not None, e.phonemize("hello world")); e.close()')
    out = subprocess.run([sys.executable, '-c', code, str(library), str(deep)], capture_output=True, text=True,
                         check=True, env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])))
    assert out.stdout.split() == ['True', 'həlˈoʊ', 'wˈɜːld']


def test_missing_data_is_an_espeak_error(tmp_path):
    library, _data = espeak.locate()
    with pytest.raises(espeak.EspeakError):
        espeak.Espeak(library, tmp_path)
