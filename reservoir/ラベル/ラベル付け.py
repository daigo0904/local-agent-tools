#!/usr/bin/env python3
"""空回りのラベルを付ける画面（この Mac の中だけ・127.0.0.1）。

    python3 reservoir/ラベル/ラベル付け.py   →  http://127.0.0.1:8770/

候補は 候補を選ぶ.py が作った ~/未踏ターゲット/ラベル/候補.json。層（怪しそう／それ以外）は見せない。
ラベルは ~/未踏ターゲット/ラベル/ラベル.json に1件ごとに保存（GitHub には上げない）。
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 候補を選ぶ import 主, 出先              # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qwc_seq import 既定の置き場, _差し込み   # noqa: E402

ラベルの道 = os.path.join(出先, "ラベル.json")


def ラベルたち():
    try:
        return json.load(open(ラベルの道, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def 見せる形(sid):
    """秘密らしい文字列を、文字列の値ごとに伏せる（JSON の文字列にまとめて掛けると引用符まで飲み込んで壊れる）。"""
    from 会話用に並べる import 伏せる
    d = _見せる形(sid)
    for h in d["手"]:
        for k, v in list(h.items()):
            if isinstance(v, str) and k != "種":
                h[k] = 伏せる(v)
    return d


def _見せる形(sid):
    d = json.load(open(os.path.join(既定の置き場, sid + ".json"), encoding="utf-8"))
    手 = []
    返り = {}
    for m in d.get("messages") or []:
        if m.get("role") == "tool":
            返り[m.get("tool_call_id")] = str(m.get("content") or "").strip().split("\n")[0][:140]
    for m in d.get("messages") or []:
        r, c = m.get("role"), m.get("content")
        if r == "user" and isinstance(c, str) and c.strip():
            手.append({"種": "注意書き" if c.startswith(_差し込み) else "頼み", "文": c[:600]})
        elif r == "assistant":
            for tc in m.get("tool_calls") or []:
                f = tc.get("function") or {}
                手.append({"種": "道具", "名": f.get("name") or "?", "引数": 主(f.get("arguments")),
                           "返り": 返り.get(tc.get("id"), "")})
            if not m.get("tool_calls") and isinstance(c, str) and c.strip():
                手.append({"種": "答え", "文": c[:500]})
    return {"id": sid, "手": 手}


class 窓口(BaseHTTPRequestHandler):
    def _送る(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._送る(200, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "画面.html"), "rb").read(),
                            "text/html; charset=utf-8")
        if u.path == "/api/list":
            候補 = json.load(open(os.path.join(出先, "候補.json"), encoding="utf-8"))
            return self._送る(200, json.dumps({"候補": 候補, "ラベル": ラベルたち()}, ensure_ascii=False))
        if u.path == "/api/s":
            sid = (parse_qs(u.query).get("id") or [""])[0]
            if not sid or "/" in sid or ".." in sid:
                return self._送る(400, "{}")
            return self._送る(200, json.dumps(見せる形(sid), ensure_ascii=False))
        self._送る(404, "{}")

    def do_POST(self):
        if urlparse(self.path).path != "/api/label":
            return self._送る(404, "{}")
        x = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if x.get("ラベル") not in ("空回り", "正常", "分からない", None):
            return self._送る(400, "{}")
        L = ラベルたち()
        if x.get("ラベル") is None:
            L.pop(x["id"], None)
        else:
            L[x["id"]] = {"ラベル": x["ラベル"], "メモ": x.get("メモ") or "", "時刻": time.strftime("%Y-%m-%dT%H:%M:%S")}
        中 = ラベルの道 + ".書きかけ"
        json.dump(L, open(中, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(中, ラベルの道)
        self._送る(200, json.dumps({"件数": len(L)}))

    def log_message(self, fmt, *a):
        # 届いた操作を残す（ラベルが保存されない原因を見るため・2026-10-06）
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % a))
        sys.stderr.flush()


if __name__ == "__main__":
    print("ラベル付け: http://127.0.0.1:8770/", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", 8770), 窓口).serve_forever()
