#!/usr/bin/env python3
"""Reproducible synthetic corpus, baseline A only. No production receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import tempfile
import time


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def state(root):
    result = {}
    for p in sorted(root.rglob('*')):
        s = p.lstat()
        item = {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid}
        if stat.S_ISREG(s.st_mode):
            raw = p.read_bytes()
            item.update(type='file', text=raw.decode('utf-8'), sha256=digest(raw))
        elif stat.S_ISDIR(s.st_mode):
            item.update(type='directory')
        elif stat.S_ISFIFO(s.st_mode):
            item.update(type='fifo')
        else:
            raise ValueError('unexpected file type: ' + str(p))
        result[p.relative_to(root).as_posix()] = item
    return result


def execute(code, root, timeout):
    argv = [sys.executable, '-I', '-c', code]
    start = time.perf_counter_ns()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen(argv, cwd=root, stdout=out, stderr=err,
                             env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'},
                             start_new_session=True, umask=0o077)
        timed_out = False
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        elapsed = time.perf_counter_ns() - start
        out.seek(0)
        err.seek(0)
        return dict(argv=argv, operation_sha256=digest(code.encode()),
                    exit_code=p.returncode, timed_out=timed_out,
                    elapsed_ns=elapsed, stdout=out.read().decode('utf-8', 'replace'),
                    stderr=err.read().decode('utf-8', 'replace'))


def check(output):
    marker = json.loads((output / 'complete.json').read_text())
    raw = (output / 'events.jsonl').read_bytes()
    cases_raw = (output / 'cases.json').read_bytes()
    cases = json.loads(cases_raw)
    rows = [json.loads(line) for line in raw.splitlines()]
    if not (len(raw) == marker['log_bytes'] and digest(raw) == marker['log_sha256']
            and digest(cases_raw) == marker['cases_sha256']
            and digest((output / 'runner.py').read_bytes()) == marker['runner_sha256']
            and len(rows) == marker['count'] == len(cases)
            and [r['id'] for r in rows] == [c['id'] for c in cases]
            and all(not r['timed_out'] for r in rows)):
        raise ValueError('incomplete or modified run; discard from aggregation')
    return rows


def run(output):
    raw = Path(__file__).with_name('cases.json').read_bytes()
    cases = json.loads(raw)
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('duplicate case ids')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'cases.json').write_bytes(raw)
    source = Path(__file__).read_bytes()
    (output / 'runner.py').write_bytes(source)
    dump(output / 'environment.json', dict(platform=platform.platform(),
         python=sys.version, uid=os.getuid(), gid=os.getgid(), arm='A',
         protection='none', child_umask='0077', acl='not captured; no explicit ACL installed',
         provenance='synthetic; not replay of historic 13 receipts'))
    with (output / 'events.jsonl').open('x') as log:
        for c in cases:
            with tempfile.TemporaryDirectory(prefix='mitou-corpus-') as td:
                root = Path(td)
                for directory in ('work', 'evidence'):
                    (root / directory).mkdir(mode=0o700)
                for name, content in c['initial'].items():
                    p = root / name
                    if name.startswith('/') or '..' in Path(name).parts:
                        raise ValueError('unsafe fixture path')
                    p.write_text(content)
                    p.chmod(0o600)
                before = state(root)
                result = execute(c['operation'], root, 3)
                after = state(root)
                observed = {k: {key: v[key] for key in ('type', 'mode', 'text') if key in v}
                            for k, v in after.items()}
                result.update(id=c['id'], kind=c['kind'], initial=before, final=after,
                              expected=c['expected_A'],
                              matched=(not result['timed_out'] and result['exit_code'] == 0
                                       and observed == c['expected_A']))
                log.write(json.dumps(result, ensure_ascii=False) + '\n')
                log.flush()
                os.fsync(log.fileno())
                if result['timed_out']:
                    raise RuntimeError('interrupted arm; no completion marker')
    lograw = (output / 'events.jsonl').read_bytes()
    dump(output / 'complete.json', dict(count=len(cases), log_bytes=len(lograw),
         log_sha256=digest(lograw), cases_sha256=digest(raw), runner_sha256=digest(source)))
    rows = check(output)
    print(json.dumps({'count': len(rows), 'matched': sum(r['matched'] for r in rows),
                      'log_bytes': len(lograw), 'arm': 'A'}))
    return all(r['matched'] for r in rows)


def self_test():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        r = execute('import time; time.sleep(2)', root, 0.05)
        assert r['timed_out'] and r['exit_code'] < 0
        output = root / 'run'
        assert run(output)
        log = output / 'events.jsonl'
        log.write_bytes(log.read_bytes()[:-1])
        try:
            check(output)
        except ValueError:
            pass
        else:
            raise AssertionError('truncated log accepted')
    print('self-test: timeout reaped, truncated log rejected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.check:
        rows = check(args.check)
        print(json.dumps({'count': len(rows), 'matched': sum(r['matched'] for r in rows)}))
    else:
        raise SystemExit(0 if run(args.output) else 1)
