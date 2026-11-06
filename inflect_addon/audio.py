"""Write 16-bit mono PCM WAV with the standard library.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    """16-bit mono PCM, written beside `path` and renamed into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.part')
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).round().astype('<i2')
    with wave.open(str(part), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())
    part.replace(path)
