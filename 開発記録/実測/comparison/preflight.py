#!/usr/bin/env python3
"""Linux witness-only preflight. Does not measure full guardrun A/B/C efficacy."""
import ast
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def witness(path):
    module = ast.parse(path.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_見届け役の中身' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('witness template missing')


def main():
    source = Path(sys.argv[1])
    manifest = json.loads((source / 'manifest.json').read_text())
    for arm in ('B', 'C'):
        assert hashlib.sha256((source / (arm + '.py')).read_bytes()).hexdigest() == manifest[arm + '_sha256']
    assert manifest['B_sha256'] != manifest['C_sha256']
    operations = {
        'forge': "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('FORGED\\n')",
        'legitimate': "from pathlib import Path; Path('output.txt').write_text('result\\n')",
    }
    rows = []
    # Rotate order even for this small preflight. No inference server involved.
    for name, operation in operations.items():
        for arm in (('B', 'C') if name == 'forge' else ('C', 'B')):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                work = root / 'work'
                evidence = root / 'evidence'
                work.mkdir()
                evidence.mkdir()
                record = evidence / '見届け.txt'
                script = root / 'witness.py'
                script.write_text(witness(source / (arm + '.py')).replace('__上限__', 'None').replace('__書ける__', repr([str(work)])))
                p = subprocess.run([sys.executable, str(script), str(record), sys.executable,
                                    '-c', operation, str(record)], cwd=work, capture_output=True,
                                   text=True, timeout=10)
                receipt = record.read_text()
                output = work / 'output.txt'
                if name == 'forge':
                    ok = (p.returncode == 0 and 'FORGED' in receipt) if arm == 'B' else (
                        p.returncode == 1 and 'FORGED' not in receipt
                        and 'landlock ABI ' in receipt and 'PermissionError' in p.stderr)
                else:
                    ok = p.returncode == 0 and output.read_text() == 'result\n'
                rows.append(dict(arm=arm, case=name, operation_sha256=hashlib.sha256(operation.encode()).hexdigest(),
                                 exit_code=p.returncode, record=receipt, stderr=p.stderr, passed=ok))
    print(json.dumps(dict(scope='witness-only preflight; not full A/B/C comparison',
                         kernel=platform.release(), manifest=manifest, rows=rows,
                         completed=len(rows), passed=sum(r['passed'] for r in rows)), ensure_ascii=False, indent=2))
    return all(r['passed'] for r in rows)


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
