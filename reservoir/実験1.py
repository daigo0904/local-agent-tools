#!/usr/bin/env python3
"""実験1：リザバーは qwc の「道具を呼ぶ流れ」を覚えられるか。判定基準は RESERVOIR.md（走らせる前に固定）。

    python3 reservoir/実験1.py
"""
import collections
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esn import ESN          # noqa: E402
from qwc_seq import 読む     # noqa: E402

始 = "<始>"


def main():
    全部 = 読む()
    n = len(全部)
    k = int(n * 0.7)
    学, 試 = [s for _, s in 全部[:k]], [s for _, s in 全部[k:]]
    語 = sorted({t for s in 学 for t in s})
    未知 = "<未知>"
    語 += [未知]
    番 = {t: i for i, t in enumerate(語)}
    V = len(語)
    def 番号(s):
        return [番.get(t, 番[未知]) for t in s]

    # ── マルコフ連鎖（直前1手・直前2手・足し1の平滑化）
    def マルコフ(次数):
        c = collections.defaultdict(collections.Counter)
        for s in 学:
            ids = [-1] * 次数 + 番号(s)
            for i in range(次数, len(ids)):
                c[tuple(ids[i - 次数:i])][ids[i]] += 1
        def 確率(前):
            cc = c.get(tuple(前))
            tot = (sum(cc.values()) if cc else 0) + V
            return [((cc[j] if cc else 0) + 1) / tot for j in range(V)]
        return 確率

    def 測る(確率の関数, 次数):
        当, 損, 数 = 0, 0.0, 0
        for s in 試:
            ids = [-1] * 次数 + 番号(s)
            for i in range(次数, len(ids)):
                p = 確率の関数(ids[i - 次数:i])
                当 += int(max(range(V), key=lambda j: p[j]) == ids[i])
                損 += -math.log(max(p[ids[i]], 1e-12))
                数 += 1
        return 当 / 数, 損 / 数, 数

    結果 = {}
    for 次数 in (1, 2):
        a, l, cnt = 測る(マルコフ(次数), 次数)
        結果["マルコフ%d" % 次数] = {"的中率": round(a, 4), "対数損失": round(l, 4)}

    # ── リザバー：入力は「今の1手」、答えは「次の1手」
    def one(i):
        v = np.zeros(V)
        v[i] = 1.0
        return v
    esn = ESN(V, V, 大きさ=300, 半径=0.9, 漏れ=0.3, 種=0)
    t0 = time.time()
    状態たち, 答えたち = [], []
    for s in 学:
        ids = 番号(s)
        st = esn.状態の並び([one(i) for i in ids[:-1]])
        状態たち.append(st)
        答えたち.append(np.array([one(i) for i in ids[1:]]))
    esn.覚える(状態たち, 答えたち)
    覚える秒 = time.time() - t0
    当, 損, 数 = 0, 0.0, 0
    t1 = time.time()
    for s in 試:
        ids = 番号(s)
        p = esn.予測(esn.状態の並び([one(i) for i in ids[:-1]]))
        for t, j in enumerate(ids[1:]):
            当 += int(int(np.argmax(p[t])) == j)
            損 += -math.log(max(float(p[t][j]), 1e-12))
            数 += 1
    一手の秒 = (time.time() - t1) / max(数, 1)
    # マルコフは各会話の1手目（<始>から）も当てているので、同じ土俵にするため2手目以降で比べ直す
    結果["リザバー"] = {"的中率": round(当 / 数, 4), "対数損失": round(損 / 数, 4)}

    def 測る2手目以降(確率の関数, 次数):
        当2, 損2, 数2 = 0, 0.0, 0
        for s in 試:
            ids = [-1] * 次数 + 番号(s)
            for i in range(次数 + 1, len(ids)):
                p = 確率の関数(ids[i - 次数:i])
                当2 += int(max(range(V), key=lambda j: p[j]) == ids[i])
                損2 += -math.log(max(p[ids[i]], 1e-12))
                数2 += 1
        return 当2 / 数2, 損2 / 数2
    for 次数 in (1, 2):
        a, l = 測る2手目以降(マルコフ(次数), 次数)
        結果["マルコフ%d" % 次数] = {"的中率": round(a, 4), "対数損失": round(l, 4)}

    差 = 結果["リザバー"]["的中率"] - 結果["マルコフ2"]["的中率"]
    合格 = 差 >= 0.02 and 結果["リザバー"]["対数損失"] < 結果["マルコフ2"]["対数損失"]
    軽い = 覚える秒 <= 10 and 一手の秒 <= 0.001
    out = {"会話": {"全部": n, "覚えさせた": len(学), "試した": len(試)}, "手の数（試した側）": 数,
           "語の数": V, "結果": 結果, "的中率の差（リザバー−マルコフ2）": round(差, 4),
           "覚える秒": round(覚える秒, 2), "1手の秒": round(一手の秒, 6),
           "判定": "合格" if (合格 and 軽い) else "不合格",
           "わけ": ("的中率の差 %+.1f ポイント（基準 +2）・対数損失 %s・軽さ %s"
                    % (差 * 100, "小さい" if 結果["リザバー"]["対数損失"] < 結果["マルコフ2"]["対数損失"] else "大きい",
                       "基準内" if 軽い else "基準外"))}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験1-結果.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
