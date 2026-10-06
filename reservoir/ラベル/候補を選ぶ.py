#!/usr/bin/env python3
"""ラベルを付ける候補を選ぶ（選び方は RESERVOIR.md「実験2の準備」で見る前に固定）。

    python3 reservoir/ラベル/候補を選ぶ.py
→ ~/未踏ターゲット/ラベル/候補.json（層は伏せて混ぜる。層は 層.json に別に残す）
"""
import collections
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qwc_seq import 流れ, 既定の置き場   # noqa: E402

出先 = os.path.expanduser("~/未踏ターゲット/ラベル")
主な引数 = ("path", "file_path", "command", "cmd", "pattern", "query", "dir", "url")


def 主(args):
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return args[:80]
    if isinstance(args, dict):
        for k in 主な引数:
            if k in args:
                return str(args[k])[:120]
    return ""


def 呼び出し(会話):
    out = []
    for m in 会話.get("messages") or []:
        for tc in m.get("tool_calls") or []:
            f = tc.get("function") or {}
            out.append((f.get("name") or "?", 主(f.get("arguments"))))
    return out


def 層A(会話):
    calls = 呼び出し(会話)
    ms = 会話.get("messages") or []
    上限 = any(isinstance(m.get("content"), str) and "maximum number of tool calls" in m["content"] for m in ms)
    最後 = next((m for m in reversed(ms) if m.get("role") == "assistant"), {})
    答えなし = bool(最後.get("tool_calls")) or not (isinstance(最後.get("content"), str) and 最後["content"].strip())
    最多 = max(collections.Counter(calls).values()) if calls else 0
    return 最多 >= 3 or len(calls) >= 15 or 上限 or 答えなし


def main():
    A, B = [], []
    for f in sorted(glob.glob(os.path.join(既定の置き場, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if len(流れ(d)) < 4:
            continue
        (A if 層A(d) else B).append(os.path.basename(f)[:-5])
    r = random.Random(0)
    a = r.sample(A, min(30, len(A)))
    b = r.sample(B, min(30, len(B)))
    並び = a + b
    r.shuffle(並び)
    os.makedirs(出先, exist_ok=True)
    json.dump(並び, open(os.path.join(出先, "候補.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"A": a, "B": b, "層Aの全数": len(A), "層Bの全数": len(B)},
              open(os.path.join(出先, "層.json"), "w"), ensure_ascii=False, indent=1)
    print("母集団 %d（層A %d・層B %d）→ 候補 %d 件（A %d・B %d）" % (len(A) + len(B), len(A), len(B), len(並び), len(a), len(b)))


if __name__ == "__main__":
    main()
