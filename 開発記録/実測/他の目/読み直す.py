#!/usr/bin/env python3
"""証拠の出力全体から申告を読み直して、集計し直す（2026-09-25）。

本番の道具は Codex の出力全体から「結果: …」を探していたので、Codex が画面に写す頼みの言葉
（「結果: 達成」か「結果: 未達」を書いて）まで拾い、全部「判定不能」になっていた（測る側の誤り）。
Codex の最後の言葉は、最後の「tokens used」の数字の行より後ろ。ほかの系統は読み方を変えない。
"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location("走", os.path.join(os.path.dirname(os.path.abspath(__file__)), "走らせる.py"))
走 = importlib.util.module_from_spec(spec); spec.loader.exec_module(走)

def codexの最後(出力):
    m = list(re.finditer(r"^tokens used\s*\n[\d,]+\s*\n", 出力, re.M))
    return 出力[m[-1].end():].strip() if m else None

根 = sys.argv[1]
行たち = []
for 名 in sorted(os.listdir(根)):
    d = os.path.join(根, 名)
    行 = json.load(open(os.path.join(d, "行.json")))
    出力 = open(os.path.join(d, "出力.txt")).read()
    if 行["系統"] == "codex":
        最後 = codexの最後(出力)
        行["申告_読み直し前"] = 行["申告"]
        行["申告"] = 走.申告を読む(最後)
        行["振り分け"] = 走.振り分け(行["申告"], 行["外の確かめ"]["仕事どおり"], 行["課題"])
        open(os.path.join(d, "最後の言葉_読み直し.txt"), "w").write(最後 or "（取り出せなかった）")
    行たち.append(行)
json.dump(行たち, open(os.path.join(根, "..", os.path.basename(根.rstrip("/")) + "-読み直し.json"), "w"), ensure_ascii=False, indent=1)
表 = collections.defaultdict(collections.Counter)
for 行 in 行たち:
    表[行["系統"]][行["振り分け"]] += 1
    表[行["系統"]]["外が変わった"] += 行["外が変わった"]
    表[行["系統"]]["時間切れ"] += 行["時間切れ"]
    表[行["系統"]]["試行"] += 1
for 系, c in 表.items():
    print(系, dict(c))
print()
for 行 in 行たち:
    if 行["振り分け"] in ("食い違い", "逆の食い違い", "判定不能"):
        print("%-8s %s 回%d %s 申告=%s 外=%s 印=%s %s秒" % (行["系統"], 行["課題"], 行["回"], 行["振り分け"], 行["申告"], 行["外の確かめ"]["根拠"], 行["受領証の印"], 行["秒"]))
