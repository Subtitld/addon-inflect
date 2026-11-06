#!/usr/bin/env python3
"""Copy espeak-ng's library and its English data into inflect_addon/espeak/.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

The frozen add-on carries exactly this folder (pyinstaller.spec refuses to
build without it), and inflect_addon/espeak.py finds it there:

    inflect_addon/espeak/libespeak-ng.so.1      (.dylib on macOS, espeak-ng.dll on Windows)
    inflect_addon/espeak/espeak-ng-data/        English only: 0.8 MB of 19
    inflect_addon/espeak/SOURCE.txt             where both came from

    python tools/stage_espeak.py --prefix build/espeak-ng/prefix --commit <sha>   # Linux, compiled
    python tools/stage_espeak.py --loader                                         # macOS, Windows

Only American English is ever spoken, and tests/test_espeak.py checks that
these files alone phonemize exactly as the whole data set does.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'inflect_addon' / 'espeak'
ENGLISH_DATA = ('phontab', 'phonindex', 'phondata', 'intonations', 'en_dict', 'lang/gmw/en-US')
LIBRARY = {'win32': 'espeak-ng.dll', 'darwin': 'libespeak-ng.dylib'}.get(sys.platform, 'libespeak-ng.so.1')


def stage(library: Path, data: Path, source: str) -> None:
    library = library.resolve()  # the file, not a symlink to it
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / 'espeak-ng-data').mkdir(parents=True)
    shutil.copyfile(library, DEST / LIBRARY)
    for name in ENGLISH_DATA:
        target = DEST / 'espeak-ng-data' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(data / name, target)
    (DEST / 'SOURCE.txt').write_text(source.rstrip() + '\n', encoding='utf-8')
    size = sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file())
    print(f'staged espeak-ng into {DEST} ({size / 1e6:.1f} MB): {source.splitlines()[0]}')


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prefix', type=Path, help='a CMake install prefix of espeak-ng')
    group.add_argument('--loader', action='store_true', help='the installed espeakng-loader wheel')
    parser.add_argument('--commit', help='the espeak-ng commit the prefix was built from')
    args = parser.parse_args(argv)
    if args.prefix:
        if not args.commit:
            parser.error('--prefix needs --commit')
        lib_dir = args.prefix / ('bin' if sys.platform == 'win32' else 'lib')
        if sys.platform.startswith('linux') and not (lib_dir / LIBRARY).exists():
            lib_dir = args.prefix / 'lib64'
        stage(lib_dir / LIBRARY, args.prefix / 'share' / 'espeak-ng-data',
              f'espeak-ng {args.commit}, compiled by tools/build_espeak.sh\n'
              f'https://github.com/espeak-ng/espeak-ng/tree/{args.commit}')
    else:
        import espeakng_loader
        from importlib.metadata import version
        stage(Path(espeakng_loader.get_library_path()), Path(espeakng_loader.get_data_path()),
              f'espeak-ng 1.52.0 (4870adfa25b1a32b4361592f1be8a40337c58d6c), from the espeakng-loader '
              f'{version("espeakng-loader")} wheel\nhttps://github.com/thewh1teagle/espeakng-loader')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
