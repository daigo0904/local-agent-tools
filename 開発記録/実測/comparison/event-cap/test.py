#!/usr/bin/env python3
"""合成コールバックで保存上限と省略件数を検査する。OS配送率は測らない。"""
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("guardrun.py")
spec = importlib.util.spec_from_file_location("guardrun", source)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class Stream:
    def __getattr__(self, name):
        return lambda _: None

results = []
with tempfile.TemporaryDirectory() as root:
    for n in (19999, 20000, 20001, 20007):
        watcher = g._出来事の見張り(root, root)
        watcher._t0 = time.monotonic()
        watcher._st = 1
        watcher._CS = Stream()
        watcher.取得状態 = "取得済み"
        paths = (ctypes.c_char_p * n)(*[(watcher.根 + "/file").encode()] * n)
        flags = (ctypes.c_uint32 * n)(*[0x1000] * n)
        watcher._受ける(None, None, n, paths, flags, None)
        # OS側の取りこぼしは別集計。属性だけの通知は保存枠を消費しない。
        watcher._受ける(None, None, 1, paths, (ctypes.c_uint32 * 1)(2), None)
        summary = watcher.止める({})
        stored = Path(summary["参照"]).read_text().splitlines()
        matched = (len(stored) == min(n, 20000)
                   and summary["出来事の数"] == min(n, 20000)
                   and summary.get("記録上限で省略した数", 0) == max(0, n - 20000)
                   and summary["落とした印"] == {"利用者側で落とした": 1})
        row = {"入力": n, "保存": len(stored), "省略": summary.get("記録上限で省略した数", 0), "一致": matched}
        print(json.dumps(row, ensure_ascii=False), flush=True)
        results.append(matched)
sys.exit(0 if all(results) else 1)
