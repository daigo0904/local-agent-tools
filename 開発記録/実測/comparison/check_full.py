#!/usr/bin/env python3
"""Validate full comparison logs independently of stored matched flags."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

CASES = ('forge', 'erase', 'truncate', 'fifo', 'write', 'mkdir', 'rename', 'unlink')
FINAL = {'write': {'input.txt': 'original\n', 'output.txt': 'result\n'},
         'mkdir': {'input.txt': 'original\n', 'sub/output.txt': 'nested\n'},
         'rename': {'renamed.txt': 'original\n'}, 'unlink': {}}


def validate(items):
    schedule = [(r, a, c) for r, order in enumerate(('ABC', 'BCA', 'CAB'))
                for c in CASES for a in order]
    if len(items) != 73:
        raise ValueError('expected 72 trials and one completion marker')
    rows, marker = items[:-1], items[-1]
    if [(r['round'], r['arm'], r['case']) for r in rows] != schedule:
        raise ValueError('missing, duplicate or out-of-order trials')
    outcomes = []
    for row in rows:
        case, arm = row['case'], row['arm']
        attack = case not in FINAL
        if row['attack'] is not attack:
            raise ValueError('case type mismatch')
        if not math.isfinite(row['elapsed']) or row['elapsed'] <= 0:
            raise ValueError('invalid elapsed time')
        receipt = row['receipt']
        ok = (receipt['終了コード'] == (1 if arm == 'C' else 3)) if attack else (
            receipt['終了コード'] == 0 and row['final'] == FINAL[case])
        if arm == 'C':
            record = row['witness']
            ok = (ok and record.get('type') == 'file'
                  and record.get('text', '').startswith('起動\n閉じ込め landlock ABI')
                  and str((receipt.get('見届け') or {}).get('閉じ込め', '')).startswith('landlock ABI'))
            if attack:
                ok = ok and 'PermissionError' in receipt.get('_出力', '')
        # Green/blue must not mask a failed command in the guarded arms.
        if attack and arm in 'BC' and receipt['判定'] in ('緑', '青'):
            ok = False
        outcomes.append(bool(ok))
    for case in CASES:
        hashes = {r['operation_sha256'] for r in rows if r['case'] == case}
        if len(hashes) != 1 or any(len(h) != 64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):
            raise ValueError('arms did not execute the same operation')
    # Report disagreements with the runner; do not silently trust its summary.
    if any(r['matched'] is not ok for r, ok in zip(rows, outcomes)):
        raise ValueError('stored matched flags disagree with independent checks')
    if marker != {'complete': 72, 'matched': sum(outcomes)}:
        raise ValueError('completion marker disagrees with trials')
    return {'complete': 72, 'matched': sum(outcomes)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    raw = args.log.read_bytes()
    items = [json.loads(line) for line in raw.splitlines()]
    result = validate(items)
    if args.self_test:
        mutations = []
        mutations.append(('missing marker', items[:-1]))
        mutations.append(('missing trial', items[1:]))
        bad = copy.deepcopy(items); bad[1] = copy.deepcopy(bad[0]); mutations.append(('duplicate trial', bad))
        bad = copy.deepcopy(items); bad[0]['operation_sha256'] = '0' * 64; mutations.append(('different operation', bad))
        bad = copy.deepcopy(items); bad[0]['matched'] = False; mutations.append(('false stored flag', bad))
        bad = copy.deepcopy(items); bad[-1]['matched'] = 71; mutations.append(('false summary', bad))
        bad = copy.deepcopy(items); bad[0]['elapsed'] = float('nan'); mutations.append(('invalid timing', bad))
        bad = copy.deepcopy(items); bad[2]['receipt']['_出力'] = ''; mutations.append(('missing denial evidence', bad))
        for label, bad in mutations:
            try:
                validate(bad)
            except ValueError:
                continue
            raise AssertionError('accepted corruption: ' + label)
        failed = copy.deepcopy(items)
        failed[12]['receipt']['終了コード'] = 1  # first legitimate A trial
        failed[12]['matched'] = False
        failed[-1]['matched'] = 71
        assert validate(failed) == {'complete': 72, 'matched': 71}
        result['corruptions_rejected'] = len(mutations)
        result['honest_failure_preserved'] = True
    result.update(log_bytes=len(raw), log_sha256=hashlib.sha256(raw).hexdigest())
    print(json.dumps(result))
    return result['matched'] == result['complete']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
