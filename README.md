# Inflect add-on for Subtitld

Offline **lightweight English text-to-speech** for
[Subtitld](https://github.com/Subtitld/subtitld), powered by
[Inflect v2](https://huggingface.co/owensong/Inflect-Micro-v2) by Owen Song, a
VITS-style model of under 10M parameters, run on
[ONNX Runtime](https://onnxruntime.ai).

- Serves the `tts.synthesize` task over Subtitld's add-on protocol.
- **Natural for its size.** One American English voice, at 24 kHz, that
  scores close to models many times larger on naturalness and intelligibility.
- **Small and fast, CPU only.** The models are 38 MB (Micro) and 16 MB (Nano).
  Measured on a 24-thread desktop CPU with the default 8 threads, Micro speaks
  about 13 times faster than real time and Nano about 30 times; on one thread,
  about 3 and 8 times.
  Under 300 MB of memory. No GPU and no torch.
- **Offline after the first line.** Each model downloads the first time its
  voice speaks, then nothing leaves the machine: no telemetry, no account.
- **English only.** Inflect speaks North American English.

## Voices

| Voice | Model | Download | Notes |
|-------|-------|----------|-------|
| American English man (Inflect Micro, best quality) | Inflect-Micro v2, 9.4M parameters | 38 MB | The default |
| American English man (Inflect Nano, smaller and faster) | Inflect-Nano v2, 4.0M parameters | 16 MB | Slightly less natural |

Both are the same fixed synthetic voice; upstream trained it without a real
speaker's recordings. Inflect does not clone voices.

## Options

Set these in **Settings ▸ Add-ons ▸ Inflect ▸ Configure**.

| Option | Default | Env var | Notes |
|--------|---------|---------|-------|
| CPU threads | automatic | `INFLECT_THREADS` | 0 picks half the logical processors, at most 8. |
| Speaking pace | 1.0 | `INFLECT_SPEED` | Inflect's own pace, 0.5 to 2.0: the model speaks faster or slower rather than the audio being stretched. |
| Variation | 0.667 | `INFLECT_VARIATION` | The model's noise scale, 0 to 1: 0 is flat and always the same, higher is livelier. |

These are the two style controls of upstream's API (`speed` and `variation`).
Each line is spoken with the seed Subtitld sends, so the same line in the same
voice comes out the same every time. Subtitld stretches a dub to fit its
subtitle itself, so the add-on ignores the rate slider; the speaking pace is
for changing how Inflect itself talks.

## How it runs

Upstream publishes an official ONNX export of each model
([Inflect-Micro-v2-ONNX](https://huggingface.co/owensong/Inflect-Micro-v2-ONNX),
[Inflect-Nano-v2-ONNX](https://huggingface.co/owensong/Inflect-Nano-v2-ONNX)),
split into a duration graph and a decoder graph, with a Python text frontend
that uses the `phonemizer` package and espeak-ng. The add-on ports that
frontend and wrapper:

- `inflect_addon/text.py`: upstream's English normalizer (numbers, money,
  dates, times, abbreviations, acronyms), its phoneme overrides and the symbol
  table, rule for rule.
- `inflect_addon/espeak.py`: phonemes from libespeak-ng through ctypes, doing
  what `phonemizer` does in upstream's configuration (punctuation kept in
  place, stress marks, quoted groups in context) without its dependencies.
- `inflect_addon/engine.py`: the two graphs, upstream's long-text splitting,
  pauses and fades.

`tests/test_espeak.py` checks the phonemes against upstream's own frontend on
the 412 prompts of upstream's evaluation set and punctuation cases (all
identical), and `tests/test_engine.py` checks the audio of both models against
upstream's ONNX wrapper for the same text and seed (within one 16-bit step).
`tools/make_fixtures.py` makes both fixtures from upstream's code.

## What is bundled, what is downloaded

| What | Size | Licence | Source |
|------|------|---------|--------|
| Add-on (bundled) | | GPL-3.0-or-later | this repository |
| espeak-ng 1.52.0, English data only (bundled) | 1.4 MB | GPL-3.0-or-later | [espeak-ng](https://github.com/espeak-ng/espeak-ng) |
| ONNX Runtime, numpy, num2words (bundled) | see the release | MIT; BSD-3-Clause; LGPL-2.1 | PyPI |
| Inflect-Micro v2 (downloaded) | 38 MB | Apache-2.0 | [owensong/Inflect-Micro-v2-ONNX](https://huggingface.co/owensong/Inflect-Micro-v2-ONNX) |
| Inflect-Nano v2 (downloaded) | 16 MB | Apache-2.0 | [owensong/Inflect-Nano-v2-ONNX](https://huggingface.co/owensong/Inflect-Nano-v2-ONNX) |

**Why GPL-3.0-or-later.** The add-on turns text into phonemes with espeak-ng,
which is GPL-3.0-or-later, and ships it in the same program; so the add-on is
GPL-3.0-or-later too. The Inflect weights and upstream's frontend code remain
Apache-2.0 (parts derive from VITS, MIT, and BigVGAN, MIT; see upstream's
`THIRD_PARTY_NOTICES.md`). The complete corresponding source of each release,
espeak-ng's included, is `inflect-<version>-source.tar.gz` on the same GitHub
release.

On Linux the build compiles espeak-ng itself from the 1.52.0 commit
(`tools/build_espeak.sh`), because the espeakng-loader wheel's library needs
glibc 2.29 and the add-on runs on 2.28. macOS and Windows use the wheel's
library, built from the same commit.

The models go to Subtitld's model folder
(`$SUBTITLD_MODELS_DIR/inflect/<model>/<revision>`), at the revisions in
`inflect_addon/pins.json`, each file checked by its sha256. An interrupted
download resumes. `$HF_ENDPOINT` points it at a mirror. The frozen Linux and
macOS builds trust the system's CA bundle (`SSL_CERT_FILE` overrides it).

Each release archive carries `THIRD_PARTY_LICENSES/README.md`, which names
the notice for every native file in it; the build fails if one has none. The
Linux archive carries libquadmath (LGPL-2.1), from numpy's wheel; its source
is attached to the same release.

Upstream asks that generated speech not be presented as a real person's
recording.

## Limits

- **English only.** A project in another language is refused with a message
  that says so. Any English (`en-GB`, `en-AU`...) is accepted and read with
  the American voice.
- **Hard words.** Rare names, places, homographs and words from other
  languages may be mispronounced; that is espeak-ng's dictionary.
- **Long lines** are cut into sentences, each spoken on its own and joined
  with a pause, as upstream does. Prosody is not planned across sentences.
- **Platforms.** Releases ship Linux x86_64 (glibc 2.28 or newer), macOS
  arm64 and Windows x86_64.
- **One line at a time.** A cancel stops the line between sentences, or stops
  the download, which resumes on the next line.

## Build

Development, in a venv of its own:

```bash
pip install -c constraints.txt -e '.[build,dev]'
pytest
```

The Linux release archive, in the AlmaLinux 8 container (needs Docker; commit
first, the Corresponding Source archives git HEAD):

```bash
tools/build_linux.sh
```

It compiles espeak-ng, freezes the bundle with `pyinstaller.spec`, gathers
`THIRD_PARTY_LICENSES/`, and writes `inflect-<version>-linux-x86_64.zip`,
the libquadmath source and the Corresponding Source tarballs. Then:

```bash
INFLECT_TEST_BINARY=$PWD/dist/inflect-addon/inflect-addon pytest tests/test_installed.py
```

On macOS or Windows, stage espeak-ng from the wheel, then freeze:

```bash
python tools/stage_espeak.py --loader
pyinstaller pyinstaller.spec --noconfirm
dist/inflect-addon/inflect-addon --self-test
```

To move to other model revisions, run `tools/pin_model.py micro=<sha> nano=<sha>`,
then regenerate the fixtures with `tools/make_fixtures.py` in a venv with
upstream's `onnx/requirements.txt`, and check that the tests still pass.

A tag `vYY.MM.N` builds, tests and publishes every platform
(`.github/workflows/release.yml`).

## Licence

GPL-3.0-or-later; see [LICENSE](LICENSE).
