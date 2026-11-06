"""Write tests/fixtures/ from upstream's own frontend and ONNX wrapper.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

Run it in a venv of its own with upstream's onnx/requirements.txt installed
(phonemizer, espeakng-loader, num2words, soundfile, onnxruntime), never the
add-on's, and point it at a download of each ONNX repository at the pinned
revision (both graphs included):

    python tools/make_fixtures.py --micro <Inflect-Micro-v2-ONNX dir> \
        --nano <Inflect-Nano-v2-ONNX dir> --prompts <modern400 prompts.jsonl>

Writes:
  phonemes.json        text -> upstream's phoneme string, for every prompt of
                       upstream's modern400 evaluation set plus punctuation cases
  parity-<model>.wav   upstream's InflectONNX output for PARITY_TEXT, seed 7
  parity.json          what produced them

Both use espeakng-loader's espeak-ng (1.52.0), not a system one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures'
PARITY_TEXT = 'Hello there! The quick brown fox, at 3:30 PM, jumps over 12 lazy dogs. Is that right?'
PARITY_SEED = 7
EXTRA = [
    'He said "hello there" and left.',
    '"Quoted," she said, "twice."',
    'It costs $3.50 (roughly) — maybe less…',
    'Dr. Smith met Mr. Jones at 10:30 AM on 12/25/2025.',
    'Call 555-1234; version 1.2.3, the 21st item!',
    'Wait... what?! No; yes: maybe.',
    '¿Qué? ¡Sí!',
    'Saskatchewan is fluorescent.',
    'The NASA and FBI teams [briefly] met {again}.',
    "It's John's «book».",
    'one, two , three ,four',
    PARITY_TEXT,
]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--micro', type=Path, required=True)
    parser.add_argument('--nano', type=Path, required=True)
    parser.add_argument('--prompts', type=Path, required=True)
    args = parser.parse_args(argv)

    import espeakng_loader
    library, data = espeakng_loader.get_library_path(), espeakng_loader.get_data_path()
    os.environ['PHONEMIZER_ESPEAK_LIBRARY'] = library
    os.environ['ESPEAK_DATA_PATH'] = data
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    EspeakWrapper.set_library(library)
    EspeakWrapper.set_data_path(data)

    sys.path[:0] = [str(args.micro / 'onnx'), str(args.micro), str(args.micro / 'runtime')]
    import inflect_nano_v2_frontend
    inflect_nano_v2_frontend._ESPEAK_CONFIGURED = True
    import inference_onnx
    import phonemizer
    import soundfile
    from inflect_vits_frontend import run_vits_frontend

    texts = [json.loads(line)['text'] for line in args.prompts.read_text(encoding='utf-8').splitlines() if line]
    phonemes = {text: run_vits_frontend(text).phoneme_text for text in texts + EXTRA}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'phonemes.json').write_text(json.dumps(phonemes, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')

    import onnxruntime
    meta = {'text': PARITY_TEXT, 'seed': PARITY_SEED, 'speed': 1.0, 'variation': 0.667,
            'phonemes': phonemes[PARITY_TEXT], 'onnxruntime': onnxruntime.__version__,
            'phonemizer': phonemizer.__version__, 'models': {}}
    for model, root in (('micro', args.micro), ('nano', args.nano)):
        tts = inference_onnx.InflectONNX(root, provider='cpu')
        rate, waveform = tts.synthesize(PARITY_TEXT, seed=PARITY_SEED)
        soundfile.write(OUT / f'parity-{model}.wav', waveform, rate, subtype='PCM_16')
        meta['models'][model] = {'samples': len(waveform), 'source': json.loads((root / 'onnx' / 'SOURCE.json').read_text())}
    (OUT / 'parity.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(phonemes)} phoneme strings; parity clips of {[m["samples"] for m in meta["models"].values()]} samples')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
