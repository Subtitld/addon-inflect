"""The add-on spoken over its wire format, in a real process.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

These run `python -m inflect_addon` and talk JSON lines to it, the way the
host does. They cover every answer the add-on owes the host without the
model or the network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

from inflect_addon import __main__ as addon, voices  # noqa: E402


@pytest.fixture()
def proc(tmp_path):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(REPO_ROOT)
    env['SUBTITLD_MODELS_DIR'] = str(tmp_path / 'models')
    env['HF_ENDPOINT'] = 'http://127.0.0.1:9'  # nothing listens: no test reaches the network
    process = subprocess.Popen([sys.executable, '-m', 'inflect_addon'], cwd=tmp_path, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    yield process
    if process.poll() is None:
        process.kill()
    process.wait()
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close()


def _send(proc, frame: dict) -> None:
    proc.stdin.write((json.dumps(frame) + '\n').encode('utf-8'))
    proc.stdin.flush()


def _recv(proc) -> dict:
    line = proc.stdout.readline()
    assert line, proc.stderr.read().decode('utf-8', 'replace')
    return json.loads(line)


def _terminal(proc, req_id: str) -> dict:
    while True:
        frame = _recv(proc)
        if frame.get('id') == req_id and frame['type'] in ('result', 'error'):
            return frame


def _synth(proc, req_id: str, tmp_path: Path, **params) -> dict:
    params.setdefault('output_path', str(tmp_path / f'{req_id}.wav'))
    _send(proc, {'id': req_id, 'type': 'tts.synthesize', 'params': params})
    return _terminal(proc, req_id)


def test_hello_lists_languages_and_voices(proc):
    hello = _recv(proc)
    assert hello['type'] == 'hello' and hello['addon'] == 'inflect' and hello['protocol'] == 1
    [capability] = hello['capabilities']
    assert capability['task'] == 'tts.synthesize'
    assert capability['languages'] == ['en-us']
    assert capability['voices'] == voices.manifest_voices()
    assert [v['id'] for v in capability['voices']] == ['inflect-micro', 'inflect-nano']
    assert capability['voice_clone'] is False


def test_requests_it_cannot_serve_get_clear_errors(proc, tmp_path):
    _recv(proc)
    _send(proc, {'type': 'ready', 'host': 'subtitld', 'host_version': 'test'})
    spanish = _synth(proc, 'a', tmp_path, text='Hola.', voice='inflect-micro', language='es')
    assert spanish['code'] == 'unsupported_language' and 'English' in spanish['message']
    assert _synth(proc, 'c', tmp_path, text='Hello.', voice='alba', language='en')['code'] == 'unsupported_voice'
    assert _synth(proc, 'd', tmp_path, text='  ', voice='inflect-nano', language='en')['code'] == 'bad_params'
    _send(proc, {'id': 'e', 'type': 'tts.synthesize', 'params': {'text': 'Hi.', 'language': 'en'}})
    assert _terminal(proc, 'e')['code'] == 'bad_params'  # no output_path
    _send(proc, {'id': 'f', 'type': 'asr.transcribe', 'params': {}})
    assert _terminal(proc, 'f')['code'] == 'bad_params'


@pytest.mark.parametrize('language', ['en-US', 'en_GB', 'en', ''])
def test_any_english_and_no_language_are_accepted(proc, tmp_path, language):
    """They get past the checks to the download, which fails here: no network."""
    _recv(proc)
    frame = _synth(proc, 'g', tmp_path, text='Hello.', voice='inflect-nano', language=language)
    assert frame['code'] == 'network_unavailable' and frame['retryable'] is True


def test_shutdown_exits_cleanly(proc):
    _recv(proc)
    _send(proc, {'type': 'shutdown'})
    assert proc.wait(timeout=10) == 0


def test_options_request_then_environment_then_default(monkeypatch):
    monkeypatch.delenv('INFLECT_SPEED', raising=False)
    monkeypatch.setenv('INFLECT_VARIATION', '0.3')
    monkeypatch.setenv('INFLECT_THREADS', 'many')
    options = addon._options({'speed': '1.5'})
    assert options == {'threads': 0, 'speed': 1.5, 'variation': 0.3}
    assert addon._options({'speed': 9, 'variation': -1}) == {'threads': 0, 'speed': 2.0, 'variation': 0.0}


def test_voices_by_id_or_model():
    assert voices.by_id('') is voices.DEFAULT
    assert voices.by_id('nano').id == 'inflect-nano'
    assert voices.by_id('kokoro') is None
