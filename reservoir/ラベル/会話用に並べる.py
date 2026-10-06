#!/usr/bin/env python3
"""候補を会話（チャット）でラベル付けするために、10件ずつ短く並べる。要約や判定はしない。

    python3 reservoir/ラベル/会話用に並べる.py 1     # 1〜10件目
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ラベル付け import 見せる形, 出先   # noqa: E402


def 一行(t, n):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n] + "…"


def main():
    回 = int(sys.argv[1])
    候補 = json.load(open(os.path.join(出先, "候補.json"), encoding="utf-8"))
    for i in range((回 - 1) * 10, min(回 * 10, len(候補))):
        d = 見せる形(候補[i])
        print("【%d】" % (i + 1))
        前, 数 = None, 0
        行 = []
        def 出す():
            if 前:
                行.append("  道具 %s %s → %s%s" % (前[0], 一行(前[1], 50), 一行(前[2], 50), "（×%d）" % 数 if 数 > 1 else ""))
        for h in d["手"]:
            if h["種"] == "道具":
                k = (h["名"], h["引数"], h["返り"])
                if k == 前:
                    数 += 1
                    continue
                出す()
                前, 数 = k, 1
                continue
            出す()
            前, 数 = None, 0
            if h["種"] == "頼み":
                行.append("  頼み：" + 一行(h["文"], 150))
            elif h["種"] == "注意書き":
                行.append("  （注意書き）")
            else:
                行.append("  答え：" + 一行(h["文"], 120))
        出す()
        print("\n".join(行))
        print()


if __name__ == "__main__":
    main()
