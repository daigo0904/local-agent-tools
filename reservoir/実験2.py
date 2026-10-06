#!/usr/bin/env python3
"""実験2：リザバーは空回りの会話を上位に並べられるか。決まりは RESERVOIR.md（ラベルの中身を見る前に固定）。

    python3 reservoir/実験2.py
ラベル（~/未踏ターゲット/ラベル/）は手元だけ。出力は集計した数字だけ（会話の中身は出さない）。
"""
import collections
import glob
import json
import math
import os
import sys

import numpy as np

ここ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ここ)
sys.path.insert(0, os.path.join(ここ, "ラベル"))
from esn import ESN, ロジスティック読み出し   # noqa: E402
from qwc_seq import 流れ, 既定の置き場         # noqa: E402
from 候補を選ぶ import 呼び出し                 # noqa: E402

置き場 = os.path.expanduser("~/未踏ターゲット/ラベル")


def auc(陽, 陰):
    """ROC-AUC（Mann-Whitney・同点は 0.5）。"""
    if not 陽 or not 陰:
        return None
    s = 0.0
    for a in 陽:
        for b in 陰:
            s += 1.0 if a > b else 0.5 if a == b else 0.0
    return s / (len(陽) * len(陰))


def main():
    L = json.load(open(os.path.join(置き場, "ラベル.json"), encoding="utf-8"))
    層 = json.load(open(os.path.join(置き場, "層.json"), encoding="utf-8"))
    印 = {k: v["ラベル"] for k, v in L.items() if v["ラベル"] in ("空回り", "正常")}
    会話 = {}
    for f in glob.glob(os.path.join(既定の置き場, "*.json")):
        try:
            会話[os.path.basename(f)[:-5]] = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            pass

    # ── 規則（対照）：同じ（道具, 主な引数）の最大繰り返し。同点は呼び出し回数で並べる
    def 規則(d):
        c = 呼び出し(d)
        return (max(collections.Counter(c).values()) if c else 0) + len(c) / 1000.0

    # ── リザバー：ラベルを付けた60件を除いた会話で覚えさせる（実験1''の作り）
    除く = set(L)
    学 = [流れ(d) for k, d in 会話.items() if k not in 除く and len(流れ(d)) >= 4]
    語 = sorted({t for s in 学 for t in s}) + ["<未知>"]
    番 = {t: i for i, t in enumerate(語)}
    V = len(語)
    eye = np.eye(V)
    esn = ESN(V, V, 大きさ=300, 半径=0.9, 漏れ=0.3, 種=0)

    def 番号(s):
        return [番.get(t, 番["<未知>"]) for t in s]
    X, y = [], []
    for s in 学:
        ids = 番号(s)
        X.append(esn.状態の並び([eye[i] for i in ids[:-1]]))
        y += ids[1:]
    読み = ロジスティック読み出し(1e-4).覚える(np.vstack(X), np.array(y), V)

    def いつもと違う度(d):
        ids = 番号(流れ(d))
        if len(ids) < 2:
            return 0.0
        p = 読み.予測(esn.状態の並び([eye[i] for i in ids[:-1]]))
        return float(np.mean(-np.log(np.maximum(p[np.arange(len(ids) - 1), ids[1:]], 1e-12))))

    名 = sorted(印)
    点 = {k: {"規則": 規則(会話[k]), "リザバー": いつもと違う度(会話[k]), "印": 印[k],
              "層": "A" if k in 層["A"] else "B"} for k in 名}

    def 二つのauc(keys):
        陽 = [k for k in keys if 点[k]["印"] == "空回り"]
        陰 = [k for k in keys if 点[k]["印"] == "正常"]
        return (auc([点[k]["規則"] for k in 陽], [点[k]["規則"] for k in 陰]),
                auc([点[k]["リザバー"] for k in 陽], [点[k]["リザバー"] for k in 陰]), len(陽), len(陰))

    規, 貯, n陽, n陰 = 二つのauc(名)
    r = np.random.default_rng(0)
    差たち = []
    for _ in range(1000):
        while True:
            s = [名[i] for i in r.integers(0, len(名), len(名))]
            a, b, p, q = 二つのauc(s)
            if p and q:
                break
        差たち.append(b - a)
    lo, hi = np.percentile(差たち, [2.5, 97.5])
    層別 = {}
    for 層名 in ("A", "B"):
        a, b, p, q = 二つのauc([k for k in 名 if 点[k]["層"] == 層名])
        層別[層名] = {"規則のAUC": None if a is None else round(a, 3), "リザバーのAUC": None if b is None else round(b, 3),
                    "空回り": p, "正常": q}
    合格 = 貯 >= 0.70 and 貯 - 規 >= 0.05
    確か = lo > 0
    out = {
        "ラベル": {"空回り": n陽, "正常": n陰, "分からない（除いた）": sum(1 for v in L.values() if v["ラベル"] == "分からない")},
        "リザバーを覚えさせた会話": len(学), "語の数": V,
        "規則のAUC": round(規, 3), "リザバーのAUC": round(貯, 3), "差（リザバー−規則）": round(貯 - 規, 3),
        "差の95%の幅": [round(float(lo), 3), round(float(hi), 3)],
        "層別": 層別,
        "判定": ("合格" if 合格 else "不合格") + ("・確かに勝った" if 合格 and 確か else "・勝ったが確かではない" if 合格 else ""),
        "わけ": "リザバー AUC %.3f（基準 0.70）・規則より %+.3f（基準 +0.05）・差の95%%幅 [%.3f, %.3f]" % (貯, 貯 - 規, lo, hi),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(ここ, "実験2-結果.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
