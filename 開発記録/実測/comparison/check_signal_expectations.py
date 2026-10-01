#!/usr/bin/env python3
"""Test expectation selection only; does not emulate an old Linux kernel."""
import ast
from pathlib import Path

source = Path('/Users/USER/bin/guardrun-印の試験')
tree = ast.parse(source.read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '閉じ込めた')
scope = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
cases = [(f'landlock ABI {abi}', '見届け役だけを殺す', abi >= 6) for abi in (1, 4, 5, 6, 8)]
cases += [(f'landlock ABI {abi}', '記録を消して成功', True) for abi in (1, 5, 8)]
cases += [('seatbelt child separation', '見届け役だけを殺す', True),
          ('なし（Linux でない）', '見届け役だけを殺す', False)]
for mode, attack, expected in cases:
    actual = scope['閉じ込めた']({'見届け': {'閉じ込め': mode}}, attack)
    assert actual is expected, (mode, attack, expected, actual)
print(f'{len(cases)}/{len(cases)} expectation branches passed; old-kernel execution not performed')
