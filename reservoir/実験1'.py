#!/usr/bin/env python3
"""実験1'：温度（リザバー）と平滑化 α（マルコフ連鎖）を検証用で決めて、実験1と同じ基準で測り直す。

決まりは RESERVOIR.md の「実験1'」（走らせる前に固定）。試す側は、値を決めるのに使わない。
    python3 reservoir/実験1\\'.py
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

温度の候補 = [0.5, 1, 2, 3, 4, 6, 8, 12, 16]
αの候補 = [0.01, 0.1, 0.5, 1]


def main():
    全部 = 読む()
    n = len(全部)
    k = int(n * 0.7)
    学, 試 = [s for _, s in 全部[:k]], [s for _, s in 全部[k:]]
    kv = int(len(学) * 0.8)
    学a, 検 = 学[:kv], 学[kv:]
    語 = sorted({t for s in 学 for t in s}) + ["<未知>"]
    番 = {t: i for i, t in enumerate(語)}
    V = len(語)

    def 番号(s):
        return [番.get(t, 番["<未知>"]) for t in s]

    def マルコフ(並び, 次数, α):
        c = collections.defaultdict(collections.Counter)
        for s in 並び:
            ids = [-1] * 次数 + 番号(s)
            for i in range(次数, len(ids)):
                c[tuple(ids[i - 次数:i])][ids[i]] += 1
        def 確率(前):
            cc = c.get(tuple(前))
            tot = (sum(cc.values()) if cc else 0) + α * V
            return np.array([((cc[j] if cc else 0) + α) / tot for j in range(V)])
        return 確率

    def 測るマルコフ(確率, 次数, 並び):
        当, 損, 数 = 0, 0.0, 0
        for s in 並び:
            ids = [-1] * 次数 + 番号(s)
            for i in range(次数 + 1, len(ids)):          # 2手目以降（リザバーと同じ位置）
                p = 確率(ids[i - 次数:i])
                当 += int(int(np.argmax(p)) == ids[i])
                損 += -math.log(max(float(p[ids[i]]), 1e-12))
                数 += 1
        return 当 / 数, 損 / 数, 数

    def one(i):
        v = np.zeros(V)
        v[i] = 1.0
        return v

    def 覚えたリザバー(並び):
        esn = ESN(V, V, 大きさ=300, 半径=0.9, 漏れ=0.3, 種=0)
        S, Y = [], []
        for s in 並び:
            ids = 番号(s)
            S.append(esn.状態の並び([one(i) for i in ids[:-1]]))
            Y.append(np.array([one(i) for i in ids[1:]]))
        return esn.覚える(S, Y)

    def 測るリザバー(esn, 並び, 温度):
        当, 損, 数 = 0, 0.0, 0
        for s in 並び:
            ids = 番号(s)
            p = esn.予測(esn.状態の並び([one(i) for i in ids[:-1]]), 温度)
            for t, j in enumerate(ids[1:]):
                当 += int(int(np.argmax(p[t])) == j)
                損 += -math.log(max(float(p[t][j]), 1e-12))
                数 += 1
        return 当 / 数, 損 / 数, 数

    # ── 検証で決める（試す側は見ない）
    esn_a = 覚えたリザバー(学a)
    検の温度 = {T: round(測るリザバー(esn_a, 検, T)[1], 4) for T in 温度の候補}
    温度 = min(検の温度, key=検の温度.get)
    検のα = {a: round(測るマルコフ(マルコフ(学a, 2, a), 2, 検)[1], 4) for a in αの候補}
    α = min(検のα, key=検のα.get)
    検のα1 = {a: round(測るマルコフ(マルコフ(学a, 1, a), 1, 検)[1], 4) for a in αの候補}
    α1 = min(検のα1, key=検のα1.get)

    # ── 決めた値で、覚えさせる側の全部で覚え直して、試す側で測る
    t0 = time.time()
    esn = 覚えたリザバー(学)
    覚える秒 = time.time() - t0
    t1 = time.time()
    ra, rl, rn = 測るリザバー(esn, 試, 温度)
    一手の秒 = (time.time() - t1) / rn
    m2a, m2l, _ = 測るマルコフ(マルコフ(学, 2, α), 2, 試)
    m1a, m1l, _ = 測るマルコフ(マルコフ(学, 1, α1), 1, 試)

    差 = ra - m2a
    損で勝つ = rl < m2l
    軽い = 覚える秒 <= 10 and 一手の秒 <= 0.001
    合格 = 差 >= 0.02 and 損で勝つ and 軽い
    out = {
        "会話": {"全部": n, "学習": len(学a), "検証": len(検), "覚えさせた（学習＋検証）": len(学), "試した": len(試)},
        "手の数（試した側）": rn, "語の数": V,
        "検証で決めた値": {"温度": 温度, "検証の対数損失（温度ごと）": 検の温度,
                        "マルコフ2の α": α, "検証の対数損失（αごと）": 検のα, "マルコフ1の α": α1},
        "結果（試した側）": {"マルコフ1": {"的中率": round(m1a, 4), "対数損失": round(m1l, 4)},
                       "マルコフ2": {"的中率": round(m2a, 4), "対数損失": round(m2l, 4)},
                       "リザバー": {"的中率": round(ra, 4), "対数損失": round(rl, 4)}},
        "的中率の差（リザバー−マルコフ2）": round(差, 4),
        "覚える秒": round(覚える秒, 2), "1手の秒": round(一手の秒, 6),
        "判定": "合格" if 合格 else "不合格",
        "わけ": "的中率の差 %+.1f ポイント（基準 +2）・対数損失 %s・軽さ %s" % (
            差 * 100, "小さい" if 損で勝つ else "大きい", "基準内" if 軽い else "基準外"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験1'-結果.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
