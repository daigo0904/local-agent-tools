#!/usr/bin/env python3
"""未踏ターゲット（リザバー）の材料を残す記録係。launchd で1分ごとに1回走る。

    1. 機械の状態（CPU の負荷・メモリ・スワップ・ollama に積まれたモデル・ollama と llama-server の資源）
       → ~/未踏ターゲット/記録/機械/YYYY-MM-DD.jsonl に1行
    2. ollama のログの写し（前回の続きから増えた分だけ）
       → ~/未踏ターゲット/記録/生/ollama-YYYY-MM-DD.log

**読み解きはしない。生のまま残すことに徹する。**読み方に誤りがあっても、生の記録から何度でもやり直せる。
ollama のログは model-guard が大きくなると切り詰めて書き直す（「ここより前は…捨てた」）ので、
前回写した最後の行を新しいファイルの中で探し、その続きから写す。見つからなければ全部写し、
継ぎ目に印を残す（重ねて写したか、取りこぼしたかを後で見分けられるように）。

心拍は guardlib の Guard.run が残す（点呼に載る）。会話の中身は扱わない。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.expanduser("~/bin"))
from guardlib import Guard   # noqa: E402

G = Guard("mitou-kiroku")
根 = os.environ.get("MITOU_KIROKU_DIR") or os.path.expanduser("~/未踏ターゲット/記録")
ログ = os.environ.get("MITOU_KIROKU_SRC") or "/opt/homebrew/var/log/ollama.log"
状態の道 = os.path.join(根, "記録係の状態.json")
今日 = lambda: time.strftime("%Y-%m-%d")


def _走る(argv, 待ち=5):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=待ち).stdout
    except Exception:                                      # noqa: BLE001
        return ""


def 機械():
    out = {"時刻": time.time(), "時刻文字": time.strftime("%Y-%m-%dT%H:%M:%S")}
    out["負荷"] = list(os.getloadavg())
    vm = _走る(["vm_stat"])
    頁 = int(re.search(r"page size of (\d+)", vm).group(1)) if "page size" in vm else 16384
    for 名, 鍵 in (("空き", "Pages free"), ("使用中", "Pages active"), ("待機", "Pages inactive"),
                  ("固定", "Pages wired down"), ("圧縮", "Pages occupied by compressor"),
                  ("スワップ入", "Swapins"), ("スワップ出", "Swapouts")):
        m = re.search(re.escape(鍵) + r":\s+(\d+)", vm)
        if m:
            v = int(m.group(1))
            out[名 + ("_回" if "スワップ" in 名 else "_MiB")] = v if "スワップ" in 名 else round(v * 頁 / 2**20, 1)
    m = re.search(r"used = ([\d.]+)M", _走る(["sysctl", "-n", "vm.swapusage"]))
    if m:
        out["スワップ使用_MiB"] = float(m.group(1))
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            ps = json.load(r)
        out["積まれたモデル"] = [{"名前": x.get("name"), "VRAM_MiB": round((x.get("size_vram") or 0) / 2**20),
                            "期限": x.get("expires_at")} for x in ps.get("models", [])]
    except Exception as e:                                 # noqa: BLE001
        out["積まれたモデル"] = None
        out["ollama_ps_失敗"] = type(e).__name__
    資源 = []
    for 行 in _走る(["ps", "-axo", "pid=,rss=,%cpu=,comm="]).splitlines():
        p = 行.split(None, 3)
        if len(p) == 4 and re.search(r"ollama|llama-server", p[3]):
            資源.append({"pid": int(p[0]), "RSS_MiB": round(int(p[1]) / 1024), "CPU%": float(p[2]),
                       "名前": os.path.basename(p[3])})
    out["ollama資源"] = 資源
    return out


def _読む(道, 既定):
    try:
        with open(道, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return 既定


def _確定書き(道, 中身):
    中 = 道 + ".書きかけ"
    with open(中, "w", encoding="utf-8") as f:
        json.dump(中身, f, ensure_ascii=False)
    os.replace(中, 道)


def ログを写す(状態):
    """前回の続きから写す。→ (写したバイト数, 継ぎ目の説明 or None)"""
    try:
        st = os.stat(ログ)
    except OSError:
        return 0, "ログが無い"
    前 = 状態.get("ログ") or {}
    継ぎ目 = None
    with open(ログ, "rb") as f:
        if 前.get("inode") == st.st_ino and 前.get("位置", 0) <= st.st_size:
            f.seek(前.get("位置", 0))
            新 = f.read()
        else:
            全部 = f.read()
            最後 = (前.get("最後の行") or "").encode("utf-8", "surrogateescape")
            i = 全部.rfind(最後) if 最後 else -1
            if i >= 0:
                新 = 全部[i + len(最後):]
                if 新.startswith(b"\n"):
                    新 = 新[1:]                          # 前回の最後の行の改行は写し済み
                継ぎ目 = "ログが書き直された（前回の最後の行の続きから写した）"
            else:
                新 = 全部
                継ぎ目 = "ログが書き直された（前回の最後の行が見つからない＝全部写した。重なり・取りこぼしの恐れあり）" if 前 else None
    # 行の途中で切らない（最後の改行まで）
    j = 新.rfind(b"\n")
    if j < 0:
        return 0, 継ぎ目
    新 = 新[:j + 1]
    道 = os.path.join(根, "生", "ollama-%s.log" % 今日())
    os.makedirs(os.path.dirname(道), exist_ok=True)
    with open(道, "ab") as w:
        if 継ぎ目:
            w.write(("--- [%s] 記録係: %s ---\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), 継ぎ目)).encode("utf-8"))
        w.write(新)
    最後の行 = 新.rstrip(b"\n").rsplit(b"\n", 1)[-1].decode("utf-8", "surrogateescape")
    with open(ログ, "rb") as f:
        f.seek(0, 2)
        位置 = f.tell()
    # 位置は「写し終えた所」= 今のファイルの中で 最後の行 が終わる所
    with open(ログ, "rb") as f:
        全部 = f.read()
    k = 全部.rfind(最後の行.encode("utf-8", "surrogateescape"))
    位置 = k + len(最後の行.encode("utf-8", "surrogateescape")) + 1 if k >= 0 else 位置
    状態["ログ"] = {"inode": st.st_ino, "位置": 位置, "最後の行": 最後の行}
    return len(新), 継ぎ目


def main():
    os.makedirs(os.path.join(根, "機械"), exist_ok=True)
    状態 = _読む(状態の道, {})
    行 = 機械()
    with open(os.path.join(根, "機械", "%s.jsonl" % 今日()), "a", encoding="utf-8") as f:
        f.write(json.dumps(行, ensure_ascii=False) + "\n")
    n, 継ぎ目 = ログを写す(状態)
    if 継ぎ目:
        G.log("記録係: " + 継ぎ目)
    状態["最後に走った"] = time.time()
    _確定書き(状態の道, 状態)
    return 0


if __name__ == "__main__":
    sys.exit(G.run(main))
