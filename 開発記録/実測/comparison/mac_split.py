#!/usr/bin/env python3
"""Candidate-only macOS witness separation; do not edit production in this builder."""
import sys
from pathlib import Path

BLOCK = '''
if sys.platform == "darwin" and 書ける is not None:
    import json as _json
    import shutil as _sh
    置 = os.path.dirname(os.path.realpath(道))
    中 = os.path.join(置, "中")
    os.makedirs(中, exist_ok=True)
    for _n in os.listdir(置):
        if _n in ("中", "見届け役.py", os.path.basename(道)):
            continue
        _src = os.path.join(置, _n)
        if os.path.isfile(_src) and not os.path.islink(_src):
            _sh.copy2(_src, os.path.join(中, _n))
    env = {k: (中 + v[len(置):] if v == 置 or v.startswith(置 + "/") else v)
           for k, v in os.environ.items()}
    # The inherited outer sandbox remains in force. This extra sandbox protects
    # witness state and limits signals from the child to processes outside it.
    _profile = ('(version 1)(allow default)'
                '(deny file-write* (require-all (subpath %s) (require-not (subpath %s))))'
                '(deny signal (require-not (target same-sandbox)))') % (
                    _json.dumps(置, ensure_ascii=False), _json.dumps(中, ensure_ascii=False))
    sys.argv[2:] = ["/usr/bin/sandbox-exec", "-p", _profile] + sys.argv[2:]
    閉じ込め = "seatbelt child separation"
'''

if __name__ == '__main__':
    src, dst = map(Path, sys.argv[1:])
    text = src.read_text()
    anchor = '書く("閉じ込め " + 閉じ込め)'
    assert text.count(anchor) == 1
    output = text.replace(anchor, BLOCK + '\n' + anchor)
    compile(output, str(dst), 'exec')
    with dst.open('x') as f:
        f.write(output)
