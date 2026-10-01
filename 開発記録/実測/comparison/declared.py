#!/usr/bin/env python3
"""CLI expectation receipts for deterministic operations; no inference needed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

CASES = [
    ('create', "open('out','w').write('result')", '緑', 0,
     {'追加': ['out'], '削除': [], '変更': []}, {'input': 'original', 'out': 'result'}, '一致'),
    ('rename', "import os;os.rename('input','renamed')", '赤', 0,
     {'追加': ['renamed'], '削除': ['input'], '変更': []}, {'renamed': 'original'}, '一致'),
    ('delete', "import os;os.unlink('input')", '赤', 0,
     {'追加': [], '削除': ['input'], '変更': []}, {}, '一致'),
    ('modify', "open('input','w').write('updated')", '緑', 0,
     {'追加': [], '削除': [], '変更': ['input']}, {'input': 'updated'}, '一致'),
    ('write_then_fail', "import sys;open('out','w').write('partial');sys.exit(3)", '失敗', 3,
     {'追加': ['out'], '削除': [], '変更': []}, {'input': 'original', 'out': 'partial'}, '一致'),
    ('wrong_expectation', "open('out','w').write('result')", '青', 0,
     {'追加': ['out'], '削除': [], '変更': []}, {'input': 'original', 'out': 'result'}, '不一致'),
]


def main():
    source, output = map(Path, sys.argv[1:])
    output.mkdir(parents=True, exist_ok=False)
    original = source.read_bytes()
    (output / 'source.py').write_bytes(original)
    (output / 'runner.py').write_bytes(Path(__file__).read_bytes())
    results = []
    for name, command, mark, exit_code, delta, expected_files, comparison in CASES:
        with tempfile.TemporaryDirectory(prefix='declared-', dir='/Users/Shared') as td:
            root = Path(td); root.chmod(0o755)
            work = root / 'work'; work.mkdir(); (work / 'input').write_text('original')
            expected = {'判定': mark, '終了コード': exit_code, '差分': delta}
            exp = root / 'expect.json'; exp.write_text(json.dumps(expected, ensure_ascii=False))
            p = subprocess.run([sys.executable, str(source), '--証明なし', '--期待', str(exp),
                                str(work), sys.executable, '-c', command],
                               env=dict(os.environ, GUARDRUN_RECORDS=str(root/'records')),
                               capture_output=True, text=True, timeout=30)
            receipt = json.loads(p.stdout)
            saved = Path(receipt['受領証'])
            if saved.is_dir(): saved /= '受領証.json'
            full = json.loads(saved.read_text())
            shutil.copytree(saved.parent, output/(name+'-records'))
            files = {f.name: f.read_text() for f in work.iterdir() if f.is_file()}
            expected_cli = 3 if mark == '赤' else exit_code
            ok = (p.returncode == expected_cli and full['終了コード'] == exit_code and files == expected_files
                  and full['期待']['結果'] == expected
                  and full['事後']['照合']['結果'] == comparison
                  and len(full['事後']['照合']['見た項目']) == 5)
            # Existing implementation reports each diff category separately.
            row = dict(case=name, command=command, initial={'input':'original'}, expected=expected,
                       preserved_records=name+'-records',
                       expected_files=expected_files, files=files, receipt=full,
                       expected_cli_exit=expected_cli, cli_exit=p.returncode, stderr=p.stderr, passed=ok)
            results.append(row)
            (output/(name+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2))
    assert source.read_bytes() == original, 'source changed during run'
    summary = {'count':len(results),'passed':sum(r['passed'] for r in results),
               'source_sha256':hashlib.sha256(original).hexdigest()}
    (output/'complete.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))
    return all(r['passed'] for r in results)


if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
