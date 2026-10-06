#!/usr/bin/env python3
"""実験3-0：規則だけで「黙り」を当てられるか（リザバーの入る余地）。決まりは RESERVOIR.md。"""
import bisect
import json
import os
import re
from datetime import datetime, timedelta

材料 = os.path.expanduser("~/未踏ターゲット/記録/過去/ollama-20260920-20260930.log")
単位 = {"µs": 1e-6, "ms": 1e-3, "s": 1.0}


def 秒(t):
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?([\d.]+)(µs|ms|s)", t) or re.fullmatch(r"(?:(\d+)h)?(\d+)m()()", t)
    if not m:
        return None
    h, mi, v, u = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + (float(v) * 単位[u] if v else 0.0)


def 読む():
    要求, 積み込み = [], []
    計算 = None
    pe = ev = None
    for l in open(材料, errors="replace"):
        if "prompt eval time =" in l:
            pe = float(re.search(r"prompt eval time =\s*([\d.]+) ms", l).group(1))
        elif re.search(r"\|\s+eval time =", l):
            ev = float(re.search(r"eval time =\s*([\d.]+) ms", l).group(1))
        elif "total time =" in l:
            計算 = ((pe or 0) + (ev or 0)) / 1000.0
            pe = ev = None
        elif 'msg="loading model via llama-server"' in l:
            m = re.search(r"time=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", l)
            if m:
                積み込み.append(datetime.fromisoformat(m.group(1)).timestamp())
        elif l.startswith("[GIN]"):
            m = re.search(r'\[GIN\] (\d{4}/\d\d/\d\d) - (\d\d:\d\d:\d\d) \| (\d+) \|\s*(\S+)\s*\|.*"(/api/\w+)"', l)
            if not m or m.group(5) not in ("/api/chat", "/api/generate"):
                continue
            終 = datetime.strptime(m.group(1) + " " + m.group(2), "%Y/%m/%d %H:%M:%S").timestamp()
            かかった = 秒(m.group(4))
            if かかった is None:
                continue
            c = 計算 if 計算 is not None else 0.0
            計算 = None
            待ち = max(0.0, かかった - c)
            状態 = int(m.group(3))
            黙り = 待ち >= 60 or (状態 != 200 and かかった >= 60)
            要求.append({"始": 終 - かかった, "終": 終, "かかった": かかった, "計算": c, "待ち": 待ち, "状態": 状態, "黙り": 黙り})
    return sorted(要求, key=lambda x: x["始"]), sorted(積み込み)


def main():
    要求, 積み込み = 読む()
    終わり順 = sorted(要求, key=lambda x: x["終"])
    終わり時刻 = [x["終"] for x in 終わり順]
    予測 = {"A": [], "B": [], "A または B": []}
    for x in 要求:
        i = bisect.bisect_right(終わり時刻, x["始"]) - 1
        a = i >= 0 and 終わり順[i]["黙り"]
        lo = bisect.bisect_left(積み込み, x["始"] - 600)
        hi = bisect.bisect_left(積み込み, x["始"])
        b = (hi - lo) >= 2
        予測["A"].append(a)
        予測["B"].append(b)
        予測["A または B"].append(a or b)
    答 = [x["黙り"] for x in 要求]
    n黙 = sum(答)
    結果 = {}
    for 名, p in 予測.items():
        tp = sum(1 for y, q in zip(答, p) if y and q)
        fp = sum(1 for y, q in zip(答, p) if q and not y)
        結果[名] = {"再現率": round(tp / n黙, 3) if n黙 else None,
                  "適合率": round(tp / (tp + fp), 3) if (tp + fp) else None,
                  "黙りと言った数": tp + fp, "当たり": tp}
    余地なし = any((r["再現率"] or 0) >= 0.8 and (r["適合率"] or 0) >= 0.5 for r in 結果.values())
    全部低い = all((r["再現率"] or 0) < 0.5 for r in 結果.values())
    判定 = ("数が足りず判断しない" if n黙 < 20 else "余地なし（リザバーはやめる）" if 余地なし
            else "余地あり（実験3へ）" if 全部低い else "余地は小さい（本人と相談）")
    待ちの分布 = sorted(x["待ち"] for x in 要求)
    out = {"chat の要求": len(要求), "積み込み": len(積み込み), "黙り": n黙, "黙りの割合": round(n黙 / len(要求), 4),
           "待ち 中央/99%/最大（秒）": [round(待ちの分布[len(待ちの分布) // 2], 2), round(待ちの分布[int(len(待ちの分布) * .99)], 1), round(待ちの分布[-1], 1)],
           "規則": 結果, "判定": 判定}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "実験3-0-結果.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
