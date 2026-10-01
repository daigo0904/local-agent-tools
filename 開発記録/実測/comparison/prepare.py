#!/usr/bin/env python3
"""Freeze production source without editing it; B differs only at Landlock application."""
import argparse
import hashlib
import json
from pathlib import Path

ANCHOR = '書く("閉じ込め " + 閉じ込め)'
INJECTION = ('# Comparison B only: retain setup/environment, omit child restriction.\n'
             '前置 = None\n閉じ込め = "comparison B: Landlock not applied"\n' + ANCHOR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    text = raw.decode()
    if text.count(ANCHOR) != 1:
        raise ValueError('source changed: anchor must occur exactly once')
    b = text.replace(ANCHOR, INJECTION).encode()
    compile(b, 'B.py', 'exec')
    compile(raw, 'C.py', 'exec')
    args.output.mkdir(parents=True, exist_ok=False)
    for name, content in [('B.py', b), ('C.py', raw)]:
        (args.output / name).write_bytes(content)
    manifest = {'source': str(args.source), 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'B_sha256': hashlib.sha256(b).hexdigest(),
                'C_sha256': hashlib.sha256(raw).hexdigest(),
                'change': INJECTION, 'scope': 'dedicated experimental copies only'}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    assert args.source.read_bytes() == raw, 'production changed during freeze'
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
