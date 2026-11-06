"""Write inflect_addon/pins.json: both ONNX exports, pinned at a revision.

Copyright (C) 2026 Subtitld contributors
SPDX-License-Identifier: GPL-3.0-or-later

    python tools/pin_model.py                 # each repository's current revision
    python tools/pin_model.py micro=<sha> nano=<sha>

Pins the two graphs of each export by size and sha256. Hugging Face's LFS
metadata gives both; they are checked against the export's own
onnx/checksums.sha256 at the same revision.
"""
import json
import sys
import urllib.request
from pathlib import Path

MODELS = {
    'micro': 'owensong/Inflect-Micro-v2-ONNX',
    'nano': 'owensong/Inflect-Nano-v2-ONNX',
}
FILES = ('onnx/duration.onnx', 'onnx/decode.onnx')
HERE = Path(__file__).resolve().parent.parent


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def pin(model: str, repo: str, revision: str | None) -> dict:
    revision = revision or json.loads(get(f'https://huggingface.co/api/models/{repo}'))['sha']
    tree = {item['path']: item for item in json.loads(get(
        f'https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=1'))}
    sums = {}
    for line in get(f'https://huggingface.co/{repo}/resolve/{revision}/onnx/checksums.sha256').decode().splitlines():
        if line.strip():
            digest, name = line.split()
            sums[f'onnx/{name}'] = digest
    files = []
    for path in FILES:
        meta = tree[path]
        sha = (meta.get('lfs') or {}).get('oid')
        if sha != sums.get(path):
            raise SystemExit(f'{repo} {path}: Hugging Face has {sha}, checksums.sha256 {sums.get(path)}')
        files.append({'path': path, 'size': meta['size'], 'sha256': sha})
    print(f"{model}: {sum(f['size'] for f in files) / 1e6:.1f} MB at {revision}")
    return {'repo': repo, 'revision': revision, 'files': files}


def main(argv: list[str]) -> int:
    revisions = dict(arg.split('=', 1) for arg in argv)
    out = {'models': {model: pin(model, repo, revisions.get(model)) for model, repo in MODELS.items()}}
    (HERE / 'inflect_addon' / 'pins.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
