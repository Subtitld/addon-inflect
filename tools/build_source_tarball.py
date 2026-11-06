#!/usr/bin/env python3
"""Build the GPL-3.0 Corresponding Source tarball attached to every release.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

The add-on is GPL-3.0-or-later and its archives carry object code of
espeak-ng (GPL-3.0-or-later) and num2words (LGPL-2.1, as bytecode). They are
downloads, not a physical product, so section 6(d) applies: the Corresponding
Source is offered from the same place, the GitHub release, at no charge.
(Adapted from addon-sanotts' tool of the same name.)

The tarball holds, at the exact revisions frozen into the binaries:

    espeak-ng-1.52.0.tar.gz        espeak-ng at ESPEAK_NG_COMMIT
    espeakng-loader-0.2.4.tar.gz   its build scripts (the macOS/Windows library)
    num2words-0.5.14.tar.gz        the PyPI sdist
    inflect-addon-<version>.tar.gz the add-on: code, spec, tools, workflow (git HEAD)
    README.md

    python tools/build_source_tarball.py --out inflect-26.11.1-source.tar.gz
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from inflect_addon import __version__  # noqa: E402

# Must match tools/build_espeak.sh and THIRD_PARTY_LICENSES/espeak-ng/SOURCE.txt.
ESPEAK_NG_COMMIT = '4870adfa25b1a32b4361592f1be8a40337c58d6c'
ESPEAK_NG_VERSION = '1.52.0'
# espeakng-loader publishes wheels only; its build.sh is in git. This commit is
# tagged "bump version to 0.2.4" upstream.
ESPEAKNG_LOADER_COMMIT = '146599e29be31bf17d99f0bcb7dbb2f92aef3d95'
ESPEAKNG_LOADER_VERSION = '0.2.4'
NUM2WORDS_VERSION = '0.5.14'


def _run(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _git_archive(url: str, commit: str, dest: Path, name: str) -> None:
    """Clone at an exact commit and archive it, checking the commit really landed."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / name
        print(f'  {url} @ {commit[:12]}', file=sys.stderr)
        _run(['git', 'clone', '--quiet', url, str(work)])
        _run(['git', 'checkout', '--quiet', commit], cwd=work)
        head = _run(['git', 'rev-parse', 'HEAD'], cwd=work)
        if head != commit:
            raise SystemExit(f'FATAL: {name} is at {head}, expected {commit}')
        _run(['git', 'archive', '--format=tar.gz', f'--prefix={name}/', '-o', str(dest / f'{name}.tar.gz'),
              'HEAD'], cwd=work)


def _sdist(package: str, version: str, dest: Path) -> None:
    with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json', timeout=60) as response:
        meta = json.load(response)
    entry = next((u for u in meta['urls'] if u['packagetype'] == 'sdist'), None)
    if entry is None:
        raise SystemExit(f'FATAL: {package} {version} has no sdist on PyPI')
    print(f"  {entry['filename']}", file=sys.stderr)
    with urllib.request.urlopen(entry['url'], timeout=300) as response:
        data = response.read()
    import hashlib
    if hashlib.sha256(data).hexdigest() != entry['digests']['sha256']:
        raise SystemExit(f"FATAL: {entry['filename']} does not match PyPI's sha256")
    (dest / entry['filename']).write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / f'inflect-{__version__}-source'
        staging.mkdir()
        print('Assembling the Corresponding Source...', file=sys.stderr)
        _git_archive('https://github.com/espeak-ng/espeak-ng', ESPEAK_NG_COMMIT, staging,
                     f'espeak-ng-{ESPEAK_NG_VERSION}')
        _git_archive('https://github.com/thewh1teagle/espeakng-loader', ESPEAKNG_LOADER_COMMIT, staging,
                     f'espeakng-loader-{ESPEAKNG_LOADER_VERSION}')
        _sdist('num2words', NUM2WORDS_VERSION, staging)
        addon = f'inflect-addon-{__version__}'
        head = _run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT)
        _run(['git', 'archive', '--format=tar.gz', f'--prefix={addon}/', '-o', str(staging / f'{addon}.tar.gz'),
              'HEAD'], cwd=REPO_ROOT)

        (staging / 'README.md').write_text(f"""# Corresponding Source: Subtitld Inflect add-on {__version__}

The complete corresponding source of the `inflect-{__version__}-*.zip` archives
on the same GitHub release, under GPL-3.0 section 6(d).

| File | What | Revision | Licence |
|---|---|---|---|
| `{addon}.tar.gz` | the add-on: code, pyinstaller.spec, tools, CI workflow | {head} | GPL-3.0-or-later |
| `espeak-ng-{ESPEAK_NG_VERSION}.tar.gz` | espeak-ng | {ESPEAK_NG_COMMIT} | GPL-3.0-or-later |
| `espeakng-loader-{ESPEAKNG_LOADER_VERSION}.tar.gz` | the scripts that build the macOS and Windows espeak-ng | {ESPEAKNG_LOADER_COMMIT} | MIT |
| `num2words-{NUM2WORDS_VERSION}.tar.gz` | number spelling, frozen as bytecode | PyPI sdist | LGPL-2.1 |

## Rebuilding

Linux: `tools/build_linux.sh` in the add-on runs everything in an AlmaLinux 8
container: `tools/build_espeak.sh` compiles espeak-ng at the commit above
(CMake, the options are in the script), `tools/stage_espeak.py` copies the
library and the English data into the package, then PyInstaller freezes it with
`pyinstaller.spec`, the dependencies pinned by `constraints.txt`.

macOS and Windows: `.github/workflows/release.yml` installs the
espeakng-loader {ESPEAKNG_LOADER_VERSION} wheel, whose library espeakng-loader's
`build.sh` compiles from the same espeak-ng commit, stages it with
`tools/stage_espeak.py --loader`, then runs PyInstaller the same way.

The Inflect v2 models (Apache-2.0) are not in the archives; they download on
first use from Hugging Face at the revisions in `inflect_addon/pins.json`.
""", encoding='utf-8')

        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.out, 'w:gz') as tar:
            tar.add(staging, arcname=staging.name)
    print(f'wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
