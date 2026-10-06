"""qwc の会話の記録 → 「道具を呼ぶ流れ」の並び。中身（人の頼みの文）は持ち出さない。"""
import glob
import json
import os

既定の置き場 = os.path.expanduser("~/.qwythos-code/sessions")
_差し込み = ("You ", "[", "<", "The ", "Your ", "Tool ", "Note:", "System")   # qwc が自動で差し込む注意書き


def 流れ(会話):
    out = []
    for m in 会話.get("messages") or []:
        r, c = m.get("role"), m.get("content")
        if r == "user":
            if isinstance(c, str) and c.strip() and not c.startswith(_差し込み):
                out.append("U")
        elif r == "assistant":
            calls = m.get("tool_calls") or []
            for tc in calls:
                name = (tc.get("function") or {}).get("name") or tc.get("name") or "?"
                out.append("T:" + name)
            if not calls and isinstance(c, str) and c.strip():
                out.append("A")
    return out


def 読む(置き場=既定の置き場, 最小=4):
    """→ [(更新時刻, 流れ)]。更新時刻の古い順。"""
    out = []
    for f in glob.glob(os.path.join(置き場, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        s = 流れ(d)
        if len(s) >= 最小:
            out.append((os.path.getmtime(f), s))
    return sorted(out)
