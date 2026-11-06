"""Inflect v2 on ONNX Runtime: text in, 24 kHz mono float32 out.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

A port of upstream's `onnx/inference_onnx.py` (Copyright Owen Song,
Apache-2.0). Upstream's export splits the model into two graphs:

    duration.onnx  tokens -> the aligned acoustic distribution (m_p, logs_p, mask)
    decode.onnx    that distribution + seeded noise -> waveform

Long text is cut at sentence punctuation, then at commas or spaces, as
upstream does; each chunk is spoken with `seed + index`, faded at its edges
and joined to the next with a pause that depends on its last mark. The same
text, seed and settings give the same audio as upstream's wrapper.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

import numpy as np
import onnxruntime as ort

from inflect_addon import text as frontend

SAMPLE_RATE = 24_000
DEFAULT_SPEED = 1.0
DEFAULT_VARIATION = 0.667
SPEED_RANGE = (0.5, 2.0)
VARIATION_RANGE = (0.0, 1.0)


class Cancelled(Exception):
    """The request was cancelled between two chunks."""


def default_threads() -> int:
    """Half the logical processors, between 1 and 8."""
    return max(1, min(8, (os.cpu_count() or 2) // 2))


def split_text(text: str, limit: int = 280) -> list[str]:
    normalized = ' '.join(text.split())
    sentences = [part.strip() for part in re.split(r'(?<=[.!?;:])\s+', normalized) if part.strip()]
    chunks: list[str] = []
    for sentence in sentences or [normalized]:
        while len(sentence) > limit:
            search = sentence[: limit + 1]
            punctuation = max(search.rfind(mark) for mark in (',', ';', ':'))
            split_at = punctuation + 1 if punctuation >= limit // 2 else sentence.rfind(' ', 0, limit + 1)
            if split_at < limit // 2:
                split_at = limit
            chunks.append(sentence[:split_at].strip())
            sentence = sentence[split_at:].strip()
        if sentence:
            chunks.append(sentence)
    return chunks


def boundary_pause_seconds(chunk: str) -> float:
    ending = chunk.rstrip()[-1:] if chunk.strip() else ''
    return {'?': 0.28, '!': 0.24, '.': 0.22, ';': 0.16, ':': 0.13, ',': 0.09}.get(ending, 0.08)


def edge_fade(waveform: np.ndarray, sample_rate: int = SAMPLE_RATE, milliseconds: float = 5.0) -> np.ndarray:
    frames = min(round(sample_rate * milliseconds / 1000.0), waveform.size // 2)
    if frames <= 0:
        return waveform
    output = waveform.copy()
    ramp = np.linspace(0.0, 1.0, frames, endpoint=True, dtype=np.float32)
    output[:frames] *= ramp
    output[-frames:] *= ramp[::-1]
    return output


class Inflect:
    """One model's two sessions, plus the espeak frontend they share."""

    def __init__(self, model_dir: str | os.PathLike, espeak, threads: int = 0):
        model_dir = Path(model_dir)
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or default_threads()
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        providers = ['CPUExecutionProvider']
        self.duration = ort.InferenceSession(str(model_dir / 'duration.onnx'), options, providers=providers)
        self.decode = ort.InferenceSession(str(model_dir / 'decode.onnx'), options, providers=providers)
        self.espeak = espeak

    def phonemes(self, text: str) -> str:
        return frontend.phonemize(self.espeak, frontend.normalize_text(text))

    def _chunk(self, text: str, *, speed: float, variation: float, seed: int) -> np.ndarray:
        tokens = frontend.tokens(self.phonemes(text))
        m_p_exp, logs_p_exp, y_mask = self.duration.run(
            ['m_p_exp', 'logs_p_exp', 'y_mask'],
            {
                'tokens': tokens,
                'lengths': np.asarray([tokens.shape[1]], dtype=np.int64),
                'length_scale': np.asarray(1.0 / speed, dtype=np.float32),
            },
        )
        rng = np.random.default_rng(seed)
        noise = rng.standard_normal(m_p_exp.shape, dtype=np.float32)
        waveform = self.decode.run(
            ['waveform'],
            {
                'm_p_exp': m_p_exp,
                'logs_p_exp': logs_p_exp,
                'y_mask': y_mask,
                'zp_noise': noise,
                'noise_scale': np.asarray(variation, dtype=np.float32),
            },
        )[0]
        return edge_fade(np.asarray(waveform, dtype=np.float32).reshape(-1))

    def synthesize(self, text: str, *, speed: float = DEFAULT_SPEED, variation: float = DEFAULT_VARIATION,
                   seed: int = 0, progress: Callable[[float], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> np.ndarray:
        normalized = ' '.join(text.split())
        if not normalized:
            raise ValueError('Text must not be empty.')
        speed = min(max(float(speed), SPEED_RANGE[0]), SPEED_RANGE[1])
        variation = min(max(float(variation), VARIATION_RANGE[0]), VARIATION_RANGE[1])
        chunks = split_text(normalized)
        pieces: list[np.ndarray] = []
        for index, chunk in enumerate(chunks):
            if cancelled is not None and cancelled():
                raise Cancelled()
            if index:
                pause = boundary_pause_seconds(chunks[index - 1])
                pieces.append(np.zeros(round(SAMPLE_RATE * pause), dtype=np.float32))
            pieces.append(self._chunk(chunk, speed=speed, variation=variation, seed=seed + index))
            if progress is not None:
                progress((index + 1) / len(chunks))
        return np.clip(np.concatenate(pieces), -1.0, 1.0)
