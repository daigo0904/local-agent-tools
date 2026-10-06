#!/usr/bin/env python3
"""頼みの文から「変えないで」の約束を拾う。**拾うのは人の言葉だけ（AI の言葉は使わない）。**

    python3 ~/bin/約束を拾う.py "test_x.py を通して。ただし app.py も test_x.py も変更してはいけません"
    → app.py, test_x.py

guardrun の「変えない」約束（期待）にそのまま渡す形で返す。（2026-10-06・本人決定で main に入れた）

**拾い方は狭く取る。**拾い間違えると、守った作業に赤い「約束違反」が付く。
  - 打ち消し（変えない・変更しない・触らない・消さない・作らない…）と**同じ文の中**の名前だけ
  - 名前と見なすのは、拡張子のある名前（app.py）か、/ を含む・/ で終わる名前（tests/）だけ。
    ふつうの単語は拾わない（2026-09-10、qwc が語の形で識別子を拾って「JavaScript」「utf8」で
    書き換えを止め、8件中7件が誤爆した。同じ穴を踏まない）
  - 「〜だけ変えて」「〜以外は変えないで」のような裏返しの言い方は拾わない（取り違えると逆になる）
"""
import re
import sys

# 打ち消し（「変える」の仲間 ＋ ない／ず／てはいけない／な）
_動詞 = r"(?:変え|変更し|変更せ|書き換え|書きかえ|いじら|いじ|触ら|触れ|さわら|編集し|編集せ|消さ|消し|削除し|削除せ|作ら|作っ|新しく作|上書きし|上書きせ|手を(?:付け|つけ|出さ))"
_打ち消し = re.compile(_動詞 + r"(?:ない|ず|ずに|ては(?:いけ|だめ|ダメ|な)|ちゃ(?:だめ|ダメ)|ないで|ません|るな|ちゃいけ)")
_英語 = re.compile(r"\b(?:do not|don't|dont|never|without)\s+(?:modify|modifying|change|changing|edit|editing|touch|touching|delete|deleting|remove|removing|create|creating)\b", re.I)
# 裏返しの言い方（取り違えると逆になるので、その文は拾わない）
_裏返し = re.compile(r"(?:以外|だけ|のみ|ほか|他の|ほかの|それ以外|except|only)")
# 名前: 拡張子あり、または / を含む（_名前らしい で確かめる）
_名 = r"[\w.\-]+(?:/[\w.\-]*)*"
_つなぎ = r"\s*(?:も|と|、|・|及び|および|や)\s*"
_強め = r"(?:絶対に|ぜったいに|一切|決して|新しく|1バイトも|１バイトも|一文字も|何も)?"
# 「NAME（も|と NAME…）［（…）］［の内容］ は|も|を|には ［強め］ 打ち消し」——打ち消しが名前を直接受ける形だけ
_日本語 = re.compile(r"(?<![\w./~-])(?P<names>" + _名 + r"(?:" + _つなぎ + _名 + r")*)\s*(?:の内容)?\s*(?:は|も|を|には)\s*"
                    + _強め + r"\s*(?=" + _動詞 + r")")
# 「…（NAME）は 打ち消し」
_括弧 = re.compile(r"[（(]\s*(?P<names>" + _名 + r"(?:" + _つなぎ + _名 + r")*)\s*[）)]\s*(?:は|も|を|には)\s*" + _強め + r"\s*(?=" + _動詞 + r")")
_英文 = re.compile(r"\b(?:do not|don't|dont|never)\s+(?:modify|change|edit|touch|delete|remove|overwrite|rename)\s+(?P<names>"
                 + _名 + r"(?:\s*(?:,|and)\s*" + _名 + r")*)", re.I)


def _名前らしい(t):
    t = t.strip("「」『』\"'`、。，．,.()（）")
    if not t or t in (".", "..", "/", "~/"):
        return None
    if "/" in t:
        return t
    if re.search(r"[A-Za-z0-9_\-]\.[A-Za-z0-9]{1,8}$", t) and not re.fullmatch(r"[0-9.]+", t):
        return t
    return None


def 拾う(文):
    """→ 約束の並び（重複なし・出てきた順）。拾えなければ []。

    打ち消しが**その名前を直接受けている**ときだけ拾う。「function.py のロジックは変更せず」は
    守るのがロジックでファイルではないので拾わない（2026-10-06、本人の実際の頼み6件中3件を
    この形で誤って拾った。直す前に固定した試験は ~/bin/約束を拾う-試験.py）。"""
    out = []
    for 一文 in re.split(r"[。\n！？!?]|(?<=[A-Za-z0-9])\.(?:\s|$)", 文 or ""):
        if _裏返し.search(一文):
            continue
        for 型 in (_日本語, _括弧, _英文):
            for m in 型.finditer(一文):
                if 型 is not _英文 and not _打ち消し.search(一文[m.end():m.end() + 20]):
                    continue
                for t in re.split(_つなぎ + r"|\s*(?:,|and)\s*", m.group("names")):
                    n = _名前らしい(t)
                    if n and n not in out:
                        out.append(n)
    return out


if __name__ == "__main__":
    print(", ".join(拾う(" ".join(sys.argv[1:]))) or "（拾えなかった）")
