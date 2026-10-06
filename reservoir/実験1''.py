#!/usr/bin/env python3
"""実験1''：リザバーの読み出しを交差エントロピーで学ぶ。決まりは RESERVOIR.md（走らせる前に固定）。"""
import collections
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from esn import ESN, ロジスティック読み出し   # noqa: E402
from qwc_seq import 読む                       # noqa: E402

λの候補 = [1e-4, 1e-3, 1e-2, 1e-1]
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
            for i in range(次数 + 1, len(ids)):
                p = 確率(ids[i - 次数:i])
                当 += int(int(np.argmax(p)) == ids[i])
                損 += -math.log(max(float(p[ids[i]]), 1e-12))
                数 += 1
        return 当 / 数, 損 / 数, 数

    esn = ESN(V, V, 大きさ=300, 半径=0.9, 漏れ=0.3, 種=0)   # 本体は固定（読み出しだけ学ぶ）
    eye = np.eye(V)

    def 状態と答え(並び):
        X, y = [], []
        for s in 並び:
            ids = 番号(s)
            X.append(esn.状態の並び([eye[i] for i in ids[:-1]]))
            y += ids[1:]
        return np.vstack(X), np.array(y)

    def 測る(読み, X, y):
        p = 読み.予測(X)
        return float(np.mean(np.argmax(p, axis=1) == y)), float(np.mean(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)))), len(y)

    Xa, ya = 状態と答え(学a)
    Xv, yv = 状態と答え(検)
    検のλ = {}
    for λ in λの候補:
        検のλ[λ] = round(測る(ロジスティック読み出し(λ).覚える(Xa, ya, V), Xv, yv)[1], 4)
    λ = min(検のλ, key=検のλ.get)
    検のα = {a: round(測るマルコフ(マルコフ(学a, 2, a), 2, 検)[1], 4) for a in αの候補}
    α = min(検のα, key=検のα.get)

    t0 = time.time()
    X, y = 状態と答え(学)
    読み = ロジスティック読み出し(λ).覚える(X, y, V)
    覚える秒 = time.time() - t0
    t1 = time.time()
    Xt, yt = 状態と答え(試)
    ra, rl, rn = 測る(読み, Xt, yt)
    一手の秒 = (time.time() - t1) / rn
    m2a, m2l, _ = 測るマルコフ(マルコフ(学, 2, α), 2, 試)

    差 = ra - m2a
    損で勝つ = rl < m2l
    軽い = 覚える秒 <= 10 and 一手の秒 <= 0.001
    out = {
        "会話": {"全部": n, "学習": len(学a), "検証": len(検), "覚えさせた": len(学), "試した": len(試)},
        "手の数（試した側）": rn, "語の数": V,
        "検証で決めた値": {"λ": λ, "検証の対数損失（λごと）": {str(k): v for k, v in 検のλ.items()},
                        "マルコフ2の α": α, "検証の対数損失（αごと）": 検のα},
        "結果（試した側）": {"マルコフ2": {"的中率": round(m2a, 4), "対数損失": round(m2l, 4)},
                       "リザバー（交差エントロピーの読み出し）": {"的中率": round(ra, 4), "対数損失": round(rl, 4)}},
        "的中率の差（リザバー−マルコフ2）": round(差, 4),
        "覚える秒（状態づくり込み）": round(覚える秒, 2), "1手の秒（状態づくり込み）": round(一手の秒, 6),
        "判定": "合格" if (差 >= 0.02 and 損で勝つ and 軽い) else "不合格",
        "わけ": "的中率の差 %+.1f ポイント（基準 +2）・対数損失 %s・軽さ %s" % (
            差 * 100, "小さい" if 損で勝つ else "大きい", "基準内" if 軽い else "基準外"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験1''-結果.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
