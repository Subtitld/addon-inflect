"""manifest.json, pins.json, pyproject and the code agree with each other.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from inflect_addon import ADDON_ID, __version__, voices
from inflect_addon import __main__ as addon

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO_ROOT / 'manifest.json').read_text(encoding='utf-8'))
PINS = json.loads((REPO_ROOT / 'inflect_addon' / 'pins.json').read_text(encoding='utf-8'))


def test_versions_agree():
    pyproject = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert MANIFEST['version'] == __version__ == pyproject['project']['version'] == addon.ADDON_VERSION
    assert re.fullmatch(r'\d\d\.\d\d\.\d+', __version__), 'versions are YY.MM.N'
    assert MANIFEST['id'] == ADDON_ID == 'inflect'


def test_manifest_lists_what_the_code_offers():
    assert MANIFEST['languages'] == list(voices.LANGUAGES)
    assert MANIFEST['voices'] == voices.manifest_voices()
    assert MANIFEST['tasks'] == ['tts.synthesize']
    assert MANIFEST['compute'] == 'cpu'
    assert MANIFEST['executable'] == 'bin/inflect-addon'
    assert set(MANIFEST['platforms']) == {'linux', 'macos', 'windows'}
    assert MANIFEST['license'].startswith('GPL-3.0-or-later')
    keys = {f['key']: f for f in MANIFEST['config_schema']['fields']}
    assert set(keys) == {'threads', 'speed', 'variation'}
    defaults = addon._options({})
    assert {k: f['default'] for k, f in keys.items()} == defaults


def test_manifest_models_are_the_pinned_ones():
    models = {m['id']: m for m in MANIFEST['models']}
    assert set(models) == {f'inflect-{name}-v2' for name in PINS['models']}
    for name, pinned in PINS['models'].items():
        entry = models[f'inflect-{name}-v2']
        assert entry['repo'] == pinned['repo'] and entry['revision'] == pinned['revision']
        assert entry['size_mb'] == round(sum(f['size'] for f in pinned['files']) / 1e6)
        assert entry['license'] == 'Apache-2.0' and entry['bundled'] is False
    assert [m['id'] for m in MANIFEST['models'] if m.get('default')] == ['inflect-micro-v2']


@pytest.mark.parametrize('model', ['micro', 'nano'])
def test_pins(model):
    pins = addon.pins(model)
    assert [p['path'] for p in pins] == ['onnx/duration.onnx', 'onnx/decode.onnx']
    for pin in pins:
        assert re.fullmatch(r'[0-9a-f]{64}', pin['sha256']) and pin['size'] > 1_000_000, pin
        assert re.fullmatch(r'[0-9a-f]{40}', pin['revision']) and pin['model'] == model, pin
    assert all(v.model in PINS['models'] for v in voices.VOICES)
