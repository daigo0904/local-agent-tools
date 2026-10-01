#!/usr/bin/env python3
"""Full guardrun comparison, synthetic cases, isolated Linux runner only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

OPERATIONS = {
    'forge': "p.write_text('起動\\n終了 0\\n')",
    'erase': 'p.unlink()',
    'truncate': "p.write_text('')",
    'fifo': 'p.unlink(); os.mkfifo(p)',
    'write': "Path('output.txt').write_text('result\\n')",
    'mkdir': "Path('sub').mkdir(); Path('sub/output.txt').write_text('nested\\n')",
    'rename': "Path('input.txt').rename('renamed.txt')",
    'unlink': "Path('input.txt').unlink()",
}


def main():
    source = Path(sys.argv[1])
    manifest = json.loads((source / 'manifest.json').read_text())
    modules = {}
    for arm in 'BC':
        path = source / (arm + '.py')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[arm + '_sha256']
        spec = importlib.util.spec_from_file_location('guardrun_' + arm, path)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        modules[arm] = g
    rows = []
    expected = {'write': {'input.txt': 'original\n', 'output.txt': 'result\n'},
                'mkdir': {'input.txt': 'original\n', 'sub/output.txt': 'nested\n'},
                'rename': {'renamed.txt': 'original\n'}, 'unlink': {}}
    for round_no, order in enumerate(('ABC', 'BCA', 'CAB')):
        for name, operation in OPERATIONS.items():
            attack = name not in expected
            code = ("from pathlib import Path; import os,sys; "
                    "t=Path(os.environ['TMPDIR']); "
                    "p=(t.parent if t.name=='中' else t)/'見届け.txt'; " + operation
                    + ('; sys.exit(3)' if attack else ''))
            for arm in order:
                root = Path(tempfile.mkdtemp(prefix='abc-', dir='/tmp'))
                root.chmod(0o755)
                w = root / 'work'; w.mkdir(mode=0o777); w.chmod(0o777)
                (w / 'input.txt').write_text('original\n'); (w / 'input.txt').chmod(0o666)
                observed = {}
                start = time.perf_counter()
                if arm == 'A':
                    t = root / 'temporary'; t.mkdir()
                    (t / '見届け.txt').write_text('起動\n')
                    p = subprocess.run([sys.executable, '-c', code], cwd=w,
                                       env=dict(os.environ, TMPDIR=str(t)), capture_output=True, text=True, timeout=15)
                    result = {'終了コード': p.returncode, '判定': None, '_出力': p.stdout+p.stderr}
                    observed['type'] = 'missing' if not (t/'見届け.txt').exists() else 'fifo' if stat.S_ISFIFO((t/'見届け.txt').lstat().st_mode) else 'file'
                else:
                    g = modules[arm]
                    original = g._見届けを読む
                    def capture(path):
                        try:
                            s = os.lstat(path)
                            observed['type'] = 'file' if stat.S_ISREG(s.st_mode) else 'fifo' if stat.S_ISFIFO(s.st_mode) else 'other'
                            if stat.S_ISREG(s.st_mode): observed['text'] = Path(path).read_text()
                        except FileNotFoundError:
                            observed['type'] = 'missing'
                        return original(path)
                    g._見届けを読む = capture
                    try:
                        result = g.run([sys.executable, '-c', code], str(w), prove=False,
                                       enforcer=g.重ね(g.別ユーザ(), g.Bubblewrap()),
                                       記録=str(root/'records'), wall_sec=10)
                    finally:
                        g._見届けを読む = original
                elapsed = time.perf_counter()-start
                final = {p.relative_to(w).as_posix():p.read_text() for p in w.rglob('*') if p.is_file()}
                rc = result['終了コード']
                ok = (rc == (1 if arm == 'C' else 3)) if attack else (rc == 0 and final == expected[name])
                if arm == 'C':
                    ok = (ok and 'landlock ABI' in str(result.get('見届け'))
                          and observed.get('type') == 'file'
                          and observed.get('text', '').startswith('起動\n閉じ込め landlock ABI'))
                row = dict(round=round_no, arm=arm, case=name, operation_sha256=hashlib.sha256(code.encode()).hexdigest(),
                           attack=attack, matched=ok, elapsed=elapsed, final=final, witness=observed, receipt=result)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                subprocess.run(['sudo','-n','rm','-rf',str(root)], check=True, capture_output=True)
    print(json.dumps({'complete':len(rows), 'matched':sum(r['matched'] for r in rows)}), flush=True)
    return all(r['matched'] for r in rows)


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
