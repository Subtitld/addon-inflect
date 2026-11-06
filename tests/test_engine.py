"""Real synthesis with both pinned models, from source, against upstream.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

The models (38 and 16 MB) download into $SUBTITLD_MODELS_DIR, or
~/.cache/subtitld/models, on the first run, checked against pins.json.
tests/fixtures/parity-<model>.wav is upstream's own ONNX wrapper speaking the
same text with the same seed (tools/make_fixtures.py).
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from inflect_addon import __main__ as addon, download, engine

pytestmark = pytest.mark.model

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
PARITY = json.loads((FIXTURES / 'parity.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module', params=['micro', 'nano'])
def model(request, espeak_engine):
    download.ensure(addon.pins(request.param), lambda *_: None, lambda: False)
    return request.param, engine.Inflect(addon.model_dir(request.param), espeak_engine, threads=2)


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as clip:
        assert clip.getframerate() == engine.SAMPLE_RATE
        return np.frombuffer(clip.readframes(clip.getnframes()), dtype='<i2').astype(np.float32) / 32768.0


def test_matches_upstream_sample_for_sample(model):
    name, inflect = model
    assert inflect.phonemes(PARITY['text']) == PARITY['phonemes']
    wav = inflect.synthesize(PARITY['text'], seed=PARITY['seed'], speed=PARITY['speed'],
                             variation=PARITY['variation'])
    reference = _read(FIXTURES / f'parity-{name}.wav')
    assert len(wav) == len(reference) == PARITY['models'][name]['samples']
    # The fixture is 16-bit: a few steps of 1/32768 between ONNX Runtime builds.
    assert np.abs(wav - reference).max() < 5e-4
    assert np.corrcoef(wav, reference)[0, 1] > 0.9999


def test_sounds_like_speech(model):
    _name, inflect = model
    wav = inflect.synthesize('Good morning. Shall we begin the recording?', seed=1)
    assert wav.dtype == np.float32 and np.abs(wav).max() <= 1.0
    seconds = len(wav) / engine.SAMPLE_RATE
    assert 1.5 < seconds < 5.0
    rms = float(np.sqrt(np.mean(wav ** 2)))
    assert 0.02 < rms < 0.5
    # The sentence pause is silence.
    assert np.sum(np.abs(wav) < 1e-4) > 0.15 * engine.SAMPLE_RATE


def test_seeds_repeat_and_vary(model):
    _name, inflect = model
    line = 'The same line, said twice.'
    a = inflect.synthesize(line, seed=3)
    assert np.array_equal(a, inflect.synthesize(line, seed=3))
    b = inflect.synthesize(line, seed=4)
    assert len(a) == len(b) and not np.array_equal(a, b)
    # No variation: the noise is scaled away, so the seed no longer matters.
    assert np.allclose(inflect.synthesize(line, seed=3, variation=0.0),
                       inflect.synthesize(line, seed=9, variation=0.0), atol=1e-5)


def test_speed_changes_the_pace(model):
    _name, inflect = model
    line = 'Speaking faster makes the line shorter.'
    normal = len(inflect.synthesize(line, seed=2))
    fast = len(inflect.synthesize(line, seed=2, speed=2.0))
    slow = len(inflect.synthesize(line, seed=2, speed=0.5))
    assert fast < 0.65 * normal and slow > 1.6 * normal


def test_cancel_between_sentences(model):
    _name, inflect = model
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) > 1

    with pytest.raises(engine.Cancelled):
        inflect.synthesize('First sentence. Second sentence. Third.', cancelled=cancelled)
