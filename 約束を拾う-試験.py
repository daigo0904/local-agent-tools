#!/usr/bin/env python3
"""約束を拾う の試験。**直す前に書いて固定した文**（拾い方を直すときに見ていない文）を含む。

    python3 ~/bin/約束を拾う-試験.py
"""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("約束を拾う", "/Users/daigo/bin/約束を拾う.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 2026-10-06、拾い方を直す前に固定した文と、期待する答え
固定 = [
    ("config.yaml を絶対に消さないで。", ["config.yaml"]),
    ("main.py のバグを直して。tests/ は触らないで。", ["tests/"]),
    ("utils.py の関数名は変えないで、中身を速くして。", []),
    ("Don't modify package.json.", ["package.json"]),
    ("server.js を書き換えて、ログを減らして。", []),
    ("README.md は変えずに、docs/ の中だけ直して。", []),          # 「だけ」がある文は拾わない（取り違え防止）
    ("index.html と style.css は編集しないでください。", ["index.html", "style.css"]),
    ("data.csv を読んで集計して。data.csv は上書きしないこと。", ["data.csv"]),
    ("Python3 で書いて。JavaScript は使わないで。", []),          # ふつうの単語は拾わない
    ("app.py を直して、test_app.py は変更しないで。", ["test_app.py"]),
]
# 直す前に誤りが出た実際の頼み（本人の qwc の記録から）
実際 = [
    ("processor.py の処理を修正してテストを通過させてください。ただし、テストファイル（test_processor.py）は絶対に書き換えないでください。", ["test_processor.py"]),
    ("function.py のロジックは変更せず、コードの説明コメントを追加してください。テストはそのままです。", []),
    ("agg.py が遅いので速くして。出力 out.txt の内容は1バイトも変えないこと。あと、どのくらい速くなったか数字で報告して。", ["out.txt"]),
    ("test_reset.py が失敗する。テストファイルは絶対に変更しないで、全部のテストが通るように counter.py のほうを直して。", []),
    ("filter_big.py のメモリ使用量を半分以下にして。実行速度も落とさないで。出力 errors.txt は変えないこと。", ["errors.txt"]),
    ("legacy_calc.py のコードが非常に読みにくいので、処理の内容を変えずにリファクタリングして可読性を高めてください。", []),
]


def main():
    ok = 0
    for 名, 組 in (("固定", 固定), ("実際", 実際)):
        for 文, 期待 in 組:
            got = m.拾う(文)
            hit = got == 期待
            ok += hit
            print("%s %s %s 期待 %s | %s" % ("○" if hit else "×", 名, got, 期待, 文[:50]))
    n = len(固定) + len(実際)
    print("%d/%d" % (ok, n))
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
