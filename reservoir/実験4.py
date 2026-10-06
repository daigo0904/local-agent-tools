#!/usr/bin/env python3
"""実験4：黙りの始まりを、規則で前もって当てられるか。決まりは RESERVOIR.md（新しいデータを見る前に固定）。

    python3 reservoir/実験4.py --読めるか     読み取れているかだけを出す（黙りの件数は出さない）
    python3 reservoir/実験4.py --判定         決まりどおりに判定する（2026-11-03 になるまで走らない）

試す側（2026-10-27〜11-03）は判定のときに1回だけ使う。それまで中身を見ない。
"""
import bisect
import glob
import json
import os
import re
import sys
import time
from datetime import datetime

根 = os.path.expanduser("~/未踏ターゲット/記録")
作る側の終わり = datetime(2026, 10, 27).timestamp()
試す側の終わり = datetime(2026, 11, 3).timestamp()
単位 = {"µs": 1e-6, "ms": 1e-3, "s": 1.0}


def 秒(t):
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)(µs|ms|s)", t) or re.fullmatch(r"(?:(\d+)h)?(\d+)m()()", t)
    if not m:
        return None
    h, mi, v, u = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + (float(v) * 単位[u] if v else 0.0)


def ログを読む(道たち):
    """→ 要求・積み込み・文脈の長さ・キャッシュ量 の並び（どれも時刻つき）"""
    要求, 積み込み, 文脈, キャッシュ = [], [], [], []
    計算 = pe = ev = None
    今 = None                                            # いちばん新しく見えた時刻（時刻の無い行に使う）
    for 道 in 道たち:
        for l in open(道, errors="replace"):
            m = re.search(r"time=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", l)
            if m:
                今 = datetime.fromisoformat(m.group(1)).timestamp()
            if "prompt eval time =" in l:
                pe = float(re.search(r"prompt eval time =\s*([\d.]+) ms", l).group(1))
            elif re.search(r"\|\s+eval time =", l):
                ev = float(re.search(r"eval time =\s*([\d.]+) ms", l).group(1))
            elif "total time =" in l:
                計算 = ((pe or 0) + (ev or 0)) / 1000.0
                pe = ev = None
            elif 'msg="loading model via llama-server"' in l and 今:
                積み込み.append(今)
            elif re.search(r"llama_context: n_ctx\s+=\s+(\d+)", l) and 今:
                文脈.append((今, int(re.search(r"n_ctx\s+=\s+(\d+)", l).group(1))))
            elif "cache state:" in l and 今:
                m2 = re.search(r"cache state: (\d+) prompts, ([\d.]+) MiB \(limits: ([\d.]+) MiB", l)
                if m2:
                    キャッシュ.append((今, float(m2.group(2)), float(m2.group(3))))
            elif l.startswith("[GIN]"):
                m3 = re.search(r'\[GIN\] (\d{4}/\d\d/\d\d) - (\d\d:\d\d:\d\d) \| (\d+) \|\s*(\S+)\s*\|.*"(/api/\w+)"', l)
                if not m3:
                    continue
                終 = datetime.strptime(m3.group(1) + " " + m3.group(2), "%Y/%m/%d %H:%M:%S").timestamp()
                今 = 終
                if m3.group(5) not in ("/api/chat", "/api/generate"):
                    continue
                かかった = 秒(m3.group(4))
                if かかった is None:
                    continue
                対応 = 計算 is not None
                c = 計算 if 対応 else 0.0
                計算 = None
                待ち = max(0.0, かかった - c)
                状態 = int(m3.group(3))
                要求.append({"始": 終 - かかった, "終": 終, "待ち": 待ち, "対応": 対応,
                           "黙り": 待ち >= 60 or (状態 != 200 and かかった >= 60)})
    return sorted(要求, key=lambda x: x["始"]), sorted(積み込み), sorted(文脈), sorted(キャッシュ)


def 機械を読む():
    out = []
    for 道 in sorted(glob.glob(os.path.join(根, "機械", "*.jsonl"))):
        for l in open(道, encoding="utf-8"):
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return sorted(out, key=lambda x: x["時刻"])


def 規則(x, 積み込み, 文脈, キャッシュ, 機械, 機械の時刻):
    s = x["始"]
    r1 = (bisect.bisect_left(積み込み, s) - bisect.bisect_left(積み込み, s - 600)) >= 2
    種類 = {n for t, n in 文脈 if s - 600 <= t < s}
    r2 = len(種類) >= 2
    i = bisect.bisect_left([t for t, _, _ in キャッシュ], s) - 1
    r3 = i >= 0 and キャッシュ[i][2] > 0 and キャッシュ[i][1] >= 0.9 * キャッシュ[i][2]
    j = bisect.bisect_left(機械の時刻, s) - 1
    r4 = j >= 0 and (機械[j].get("空き_MiB", 1e9) + 機械[j].get("待機_MiB", 0)) < 1024
    return {"R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r1 or r2 or r3 or r4}


def 始まりの候補(要求):
    """始まる前に終わった直前の要求が黙りでなかった要求（または直前10分に要求が無い）。→ [(要求, 始まりか)]"""
    終わり順 = sorted(要求, key=lambda x: x["終"])
    終わり時刻 = [x["終"] for x in 終わり順]
    out = []
    for x in 要求:
        i = bisect.bisect_right(終わり時刻, x["始"]) - 1
        直前 = 終わり順[i] if i >= 0 else None
        if 直前 is None or 直前["終"] < x["始"] - 600 or not 直前["黙り"]:
            out.append((x, x["黙り"]))
    return out


def main():
    ログ = sorted(glob.glob(os.path.join(根, "生", "ollama-*.log")))
    要求, 積み込み, 文脈, キャッシュ = ログを読む(ログ)
    機械 = 機械を読む()
    機械の時刻 = [m["時刻"] for m in 機械]

    if "--読めるか" in sys.argv:
        抜け = sum(1 for a, b in zip(機械の時刻, 機械の時刻[1:]) if b - a > 300)
        # 機械の記録がある期間の要求のうち、5分以内の機械の行と結べた割合（R4 が使えるか）
        範囲内 = [x for x in 要求 if 機械 and 機械の時刻[0] <= x["始"] <= 機械の時刻[-1]]
        結べた = sum(1 for x in 範囲内
                  if x["始"] - 機械の時刻[bisect.bisect_left(機械の時刻, x["始"]) - 1] <= 300)
        print(json.dumps({
            "ログのファイル": len(ログ), "chat の要求": len(要求),
            "計算時間と対応が取れた割合": round(sum(x["対応"] for x in 要求) / max(len(要求), 1), 3),
            "積み込み": len(積み込み), "文脈の長さの記録": len(文脈), "キャッシュの記録": len(キャッシュ),
            "機械の記録": len(機械), "機械の記録の5分超の抜け": 抜け,
            "機械の期間内の要求": len(範囲内), "うち機械の行と結べた割合": round(結べた / max(len(範囲内), 1), 3),
            "期間": [time.strftime("%m-%d %H:%M", time.localtime(機械の時刻[0])) if 機械 else None,
                   time.strftime("%m-%d %H:%M", time.localtime(機械の時刻[-1])) if 機械 else None],
            "注意": "黙りの件数は出さない（判定まで見ない）",
        }, ensure_ascii=False, indent=1))
        return 0

    if "--判定" in sys.argv:
        if time.time() < 試す側の終わり:
            print("まだ走らせない：試す側（2026-10-27〜11-03）が溜まりきるのは 2026-11-03 0:00。")
            return 2
        試す = [x for x in 要求 if 作る側の終わり <= x["始"] < 試す側の終わり]
        候補 = 始まりの候補(試す)
        n始 = sum(1 for _, y in 候補 if y)
        結果 = {}
        for 名 in ("R1", "R2", "R3", "R4", "R5"):
            p = [規則(x, 積み込み, 文脈, キャッシュ, 機械, 機械の時刻)[名] for x, _ in 候補]
            y = [b for _, b in 候補]
            tp = sum(1 for a, b in zip(p, y) if a and b)
            fp = sum(1 for a, b in zip(p, y) if a and not b)
            結果[名] = {"再現率": round(tp / n始, 3) if n始 else None,
                      "適合率": round(tp / (tp + fp), 3) if tp + fp else None}
        余地なし = any((r["再現率"] or 0) >= 0.8 and (r["適合率"] or 0) >= 0.5 for r in 結果.values())
        全部低い = all((r["再現率"] or 0) < 0.5 for r in 結果.values())
        判定 = ("判断しない（始まりが20件未満）" if n始 < 20 else "余地なし" if 余地なし
                else "余地あり（実験5へ）" if 全部低い else "その間（本人と相談）")
        out = {"試す側の要求": len(試す), "始まりが起こりうる要求": len(候補), "始まり": n始, "規則": 結果, "判定": 判定}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験4-結果.json"), "w"),
                  ensure_ascii=False, indent=1)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
