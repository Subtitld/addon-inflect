"""Shared fixtures: espeak-ng, as the add-on finds it.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from inflect_addon import espeak  # noqa: E402


@pytest.fixture(scope='session')
def espeak_engine():
    library, data = espeak.locate()
    engine = espeak.Espeak(library, data)
    yield engine
    engine.close()
