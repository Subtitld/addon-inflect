"""The frozen binary, unpacked from its release archive the way Subtitld installs it.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

$INFLECT_TEST_BINARY names the binary; without it these tests skip (and the
release workflow refuses skipped tests). The binary downloads both models
(54 MB) into $SUBTITLD_MODELS_DIR, with nothing but what is in its own bundle,
then speaks with each voice and cancels a line.

    INFLECT_TEST_BINARY=dist/inflect-addon/inflect-addon pytest tests/test_installed.py
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import wave
from pathlib import Path

import pytest

BINARY = os.environ.get('INFLECT_TEST_BINARY', '')
pytestmark = pytest.mark.skipif(not BINARY, reason='INFLECT_TEST_BINARY is not set')


class Addon:
    """The binary on the protocol, with a watchdog so a hang fails instead of stalling CI."""

    def __init__(self, tmp_path: Path, timeout: float):
        env = dict(os.environ, SUBTITLD_TEMP_DIR=str(tmp_path))
        env.setdefault('SUBTITLD_MODELS_DIR', str(tmp_path / 'models'))
        self.proc = subprocess.Popen([BINARY], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=env)
        self.timer = threading.Timer(timeout, self.proc.kill)
        self.timer.start()

    def send(self, frame: dict) -> None:
        self.proc.stdin.write((json.dumps(frame) + '\n').encode())
        self.proc.stdin.flush()

    def read(self) -> dict:
        line = self.proc.stdout.readline()
        assert line, 'the add-on closed its output (crashed or timed out)'
        return json.loads(line)

    def until_terminal(self, req_id: str, on_progress=None) -> dict:
        while True:
            frame = self.read()
            if frame.get('id') != req_id:
                continue
            if frame['type'] in ('result', 'error'):
                return frame
            if on_progress is not None:
                on_progress(frame)

    def close(self) -> int:
        try:
            self.send({'type': 'shutdown'})
        except (BrokenPipeError, OSError):
            pass
        try:
            return self.proc.wait(timeout=15)
        finally:
            self.timer.cancel()
            self.proc.kill()


def test_version():
    out = subprocess.run([BINARY, '--version'], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == 'inflect-addon 26.11.1'


def test_self_test_phonemizes_and_runs_onnx():
    out = subprocess.run([BINARY, '--self-test'], capture_output=True, text=True, encoding='utf-8', timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    report = json.loads(out.stdout.strip().splitlines()[-1])
    assert report['ok'] is True and report['espeak_bundled'] is True and report['espeak'] == '1.52.0'


def test_speaks_with_each_voice_then_cancels(tmp_path):
    addon = Addon(tmp_path, timeout=900)
    try:
        hello = addon.read()
        assert hello['type'] == 'hello' and hello['addon'] == 'inflect'
        voice_ids = [v['id'] for v in hello['capabilities'][0]['voices']]
        assert voice_ids == ['inflect-micro', 'inflect-nano']
        addon.send({'type': 'ready', 'host': 'test'})

        for index, voice in enumerate(voice_ids):
            out = tmp_path / f'{voice}.wav'
            addon.send({'id': voice, 'type': 'tts.synthesize', 'params': {
                'text': 'Good morning. The meeting starts at 9:30 AM, in room 204.', 'voice': voice,
                'language': 'en-US', 'seed': 5, 'output_path': str(out)}})
            result = addon.until_terminal(voice)
            assert result['type'] == 'result', result
            assert result['data']['sample_rate'] == 24000 and result['data']['duration_sec'] > 2
            with wave.open(str(out)) as clip:
                assert clip.getframerate() == 24000 and clip.getnframes() > 48000

        cancelled = []

        def on_progress(frame):
            if frame.get('message') == 'Speaking...' and not cancelled:
                cancelled.append(frame['value'])
                addon.send({'type': 'cancel', 'target': 'c'})

        addon.send({'id': 'c', 'type': 'tts.synthesize', 'params': {
            'text': 'This line is long enough to be interrupted before it ends. ' * 12,
            'voice': 'inflect-micro', 'language': 'en', 'output_path': str(tmp_path / 'c.wav')}})
        error = addon.until_terminal('c', on_progress)
        assert cancelled and error['type'] == 'error' and error['code'] == 'cancelled'
        assert not (tmp_path / 'c.wav').exists()
    finally:
        assert addon.close() == 0
