"""The add-on's voices: one per Inflect model, both the same American man.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

Inflect v2 has a single fixed voice. Micro (9.4M parameters) sounds better;
Nano (4.0M) is a third of the download and about twice as fast. Each model
downloads the first time its voice speaks.
"""

from __future__ import annotations

from dataclasses import dataclass

SAMPLE_RATE = 24000
# Inflect speaks North American English: an English project of any variety
# gets it, said with an American accent.
LANGUAGES = ('en-us',)
LANGUAGE_NAMES = {'en': 'English'}


@dataclass(frozen=True)
class Voice:
    id: str
    model: str          # key in pins.json
    display_name: str


VOICES = (
    Voice('inflect-micro', 'micro', 'American English man (Inflect Micro, best quality)'),
    Voice('inflect-nano', 'nano', 'American English man (Inflect Nano, smaller and faster)'),
)
DEFAULT = VOICES[0]


def by_id(voice_id: str) -> Voice | None:
    """The voice, by its id or its model's name. '' gives the default."""
    if not voice_id:
        return DEFAULT
    return next((v for v in VOICES if voice_id in (v.id, v.model)), None)


def primary_language(raw) -> str:
    """'en' from 'en-US', 'en_GB', 'EN'..., '' when blank."""
    return str(raw or '').strip().replace('_', '-').split('-', 1)[0].lower()


def manifest_voices() -> list[dict]:
    return [{'id': v.id, 'language': LANGUAGES[0], 'display_name': v.display_name, 'sample_rate': SAMPLE_RATE}
            for v in VOICES]
