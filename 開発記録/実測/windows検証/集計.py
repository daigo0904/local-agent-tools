#!/usr/bin/env python3
"""reset-check のログから、判定基準.md の各項目を 勝ち／負け／参考／測れず に分ける。

    python3 集計.py <ログ> > 結果.md

基準はここに写してある（判定基準.md と同じもの）。結果を見てから変えないこと。
"""
import json
import re
import sys
from collections import defaultdict

行 = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
拾い = defaultdict(lambda: defaultdict(list))      # ジョブ → 札 → [本文]
for x in 行:
    m = re.match(r"^([^\t]+)\t[^\t]*\t\S+Z (.*)$", x)
    if not m:
        continue
    ジョブ, 本文 = m.group(1), m.group(2)
    t = re.match(r"^【([^】]+)】(.*)$", 本文)
    if t:
        拾い[ジョブ][t.group(1)].append(t.group(2))


def json行(xs, 鍵):
    for x in reversed(xs):
        x = x.strip()
        if x.startswith("{") and 鍵 in x:
            try:
                return json.loads(x)
            except ValueError:
                pass
    return None


def 壁(xs):
    まる = [x.split()[1] for x in xs if x.strip().startswith("○")]
    ほし = [x.split()[1] for x in xs if x.strip().startswith("★")]
    return まる, ほし


出 = []
def 書く(番, 項目, 判, 根拠):
    出.append("| %s | %s | **%s** | %s |" % (番, 項目, 判, 根拠.replace("|", "／")[:300]))


# ── Windows ──
W = next((v for k, v in 拾い.items() if k.startswith("windows")), None)
if W is None:
    出.append("\n**Windows のジョブの出力がありません**（枠が戻っていない／走っていない）。\n")
else:
    まる, ほし = 壁(W["W1"])
    # ★は量・CPU の中だけならよい（0fb93de で CPU が○になり得る・判定基準.md の変えた記録）
    書く("W1", "証明（now）", "勝ち" if len(まる) + len(ほし) == 12 and set(ほし) <= {"CPU", "量"} else "負け" if まる or ほし else "測れず",
         "○%d ★%s（CPU は %s）" % (len(まる), "・".join(ほし), "★" if "CPU" in ほし else "○"))
    j = json行(W["W2"], "通った")
    書く("W2", "印の試験（now）", "測れず" if not j else "勝ち" if j["通った"] == j["全部"] else "負け",
         json.dumps(j, ensure_ascii=False) if j else "")
    j = json行(W["W3"], "件数")
    書く("W3", "実測（now）", "測れず" if not j else "勝ち" if j["照合"].get("一致") == j["件数"] and not j["被害"] else "負け",
         "一致 %s/%s・被害 %s・上乗せ %sms" % (j["照合"].get("一致"), j["件数"], j["被害"], j["上乗せms"]) if j else "")
    t = " ".join(W["W4"])
    ok = ("期待どおり" in t and "'結果': '一致'" in t and "'結果': '不一致'" in t and "'結果': '未宣言'" in t)
    書く("W4", "受領証の照合", "勝ち" if ok else "負け" if t else "測れず", t[:200])
    t = " ".join(W["W5"])
    書く("W5", "ファイル1つの許可", "勝ち" if "許可: 77" in t else "負け" if t else "測れず", t)
    t = " ".join(W["W6"])
    読めた = [s.split(" が中から")[0].strip() for s in t.replace("★ 秘密", "").split("／") if "が中から" in s]
    名指し = [r"\.ssh", r"\.aws", r"\.gnupg", r"Keychains", r"\.openclaw\\\.env", r"\.openclaw\\state"]
    漏れ = [p for p in 読めた if any(re.search(n + "$", p) for n in 名指し)]
    書く("W6", "秘密の対照", "測れず" if not t else "勝ち" if not 漏れ and len(読めた) == 7 else "負け",
         "読めた %d件・名指しの漏れ %s" % (len(読めた), 漏れ or "なし"))
    j = next((json.loads(x.split("まとめ", 1)[1]) for x in W["W7"] if x.startswith("まとめ")), None)
    if j:
        n, s = j["同じプロセス・now"], j["同じプロセス・sid"]
        全緑 = all(v["緑で書けた"].split("/")[0] == v["緑で書けた"].split("/")[1] for v in j.values())
        差 = n["中央値ms"] - s["中央値ms"]
        書く("W7", "時間（同じプロセス）", "勝ち" if 全緑 and 差 >= 300 else "負け",
             "now %dms → sid %dms（差 %dms）・全部緑で書けた=%s" % (n["中央値ms"], s["中央値ms"], 差, 全緑))
        c, d = j["コマンド・now"], j["コマンド・sid"]
        書く("W7c", "時間（コマンド・参考）", "参考", "now %dms → sid %dms（差 %dms）" % (
            c["中央値ms"], d["中央値ms"], c["中央値ms"] - d["中央値ms"]))
    else:
        書く("W7", "時間", "測れず", " ".join(W["W7"])[:200])
    まる, ほし = 壁(W["W8証明"])
    ji, jj = json行(W["W8印"], "通った"), json行(W["W8実測"], "件数")
    ok = (len(まる) + len(ほし) == 12 and set(ほし) <= {"CPU", "量"} and ji and ji["通った"] == ji["全部"]
          and jj and jj["照合"].get("一致") == jj["件数"] and not jj["被害"])
    書く("W8", "sid の証明・印・実測", "勝ち" if ok else "負け" if (まる or ji or jj) else "測れず",
         "証明 ○%d ★%s・印 %s・実測 %s" % (len(まる), "・".join(ほし), ji and "%d/%d" % (ji["通った"], ji["全部"]),
                                         jj and "%s/%s 被害%s" % (jj["照合"].get("一致"), jj["件数"], jj["被害"])))

# ── Linux ──
for ジョブ, L in sorted(拾い.items()):
    if not ジョブ.startswith("linux"):
        continue
    版 = "22.04" if "22.04" in ジョブ else "24.04"
    参考 = 版 == "24.04"
    def 判(ok, 有):
        return "測れず" if not 有 else ("参考・" if 参考 else "") + ("勝ち" if ok else "負け")
    j = next((json.loads(x.split("閉じ込め", 1)[1]) for x in L["L1"] if x.startswith("閉じ込め")), None)
    ok = j and ((j["Landlock版"] >= 1 and str(j["閉じ込め"]).startswith("landlock"))
                or (j["Landlock版"] < 1 and str(j["閉じ込め"]).startswith("なし")))
    書く("L1/" + 版, "閉じ込め", 判(ok, j), json.dumps(j, ensure_ascii=False) if j else "")
    まる, ほし = 壁(L["L2"])
    書く("L2/" + 版, "証明", 判(len(まる) == 12, まる or ほし), "○%d ★%s" % (len(まる), "・".join(ほし)))
    j = json行(L["L3"], "通った")
    書く("L3/" + 版, "印の試験", 判(j and j["通った"] == j["全部"], j), json.dumps(j, ensure_ascii=False) if j else "")
    j = json行(L["L4"], "件数")
    書く("L4/" + 版, "実測", 判(j and j["照合"].get("一致") == j["件数"] and not j["被害"], j),
         "一致 %s/%s・被害 %s・上乗せ %sms" % (j["照合"].get("一致"), j["件数"], j["被害"], j["上乗せms"]) if j else "")
    t = next((x for x in L["L5"] if "/home/runner/外.txt" in x), "")
    書く("L5/" + 版, "外に書く", 判("Read-only" in t, t), t[:200])

print("# リセット後の検証 結果\n\n基準: 判定基準.md（走らせる前に書いたもの）\n")
print("| 番 | 項目 | 判定 | 根拠 |\n|---|---|---|---|")
print("\n".join(出))
勝 = sum("**勝ち**" in x for x in 出)
負 = sum("| **負け** |" in x for x in 出)
print("\n勝ち %d・負け %d（参考・測れずを除く）" % (勝, 負))
print("\n**sid を入れてよいのは W7 と W8 が両方「勝ち」のときだけ。**")
