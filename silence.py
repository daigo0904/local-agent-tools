#!/usr/bin/env python3
"""silence — 黙って消えることを、この家では起こせなくする。

## 何を前提にしているか

**この家のものは落ちずに黙る。** launchd の KeepAlive はプロセスの死にしか
効かないので、「立っているのに働いていない」は全部素通りする。
そこまでは見張り一式が扱ってきた。**残っていたのは、その一段外側。**

  誰も見ていない  2026-09-12 に数えたら、launchd の16本のうち **7本は跡を
                  1つも残していなかった**（backup・gateway・line-proxy・
                  line-sync・line-tunnel・tidy-files・vault-tidy）。
                  心拍を残す13本のうち **7本は誰も見ていなかった**。
                  openclaw-update の心拍は5.8日前、house-brief は27時間前。
                  **どちらも、誰も何も言っていない。**
  台帳が手書き    見張る相手は watchdog のソースに名前で書いてある。だから
                  **明日1本足すと、見られないまま静かに増える。**
                  穴が開くのではなく、穴が開いても分からない形をしている。
  心拍は本人が書く guardlib の beat() は失敗した回にも残す（相手が答えない
                  ことと見張りが死んだことは別だから、これは正しい）。
                  だが結果として **「走って、何もせず、0で終わる」は
                  健全とまったく同じ見た目になる。**

## だから、台帳を手で書くのをやめた

**契約は launchd が持っている。** plist の StartInterval /
StartCalendarInterval / KeepAlive が、その仕事の期限そのものである。
**受領証も launchd が持っている。** `launchctl print` の runs と
last exit code は、**その仕事自身には書けない。**

    契約   plist の間隔・時刻・常駐かどうか        ← OS が持っている
    受領証 launchctl の runs / last exit code      ← **本人には書けない**
    自己申告 ~/.openclaw/pulse/<名前>.json          ← 本人が書く（嘘をつける）
    仕事の跡 plist の StandardOutPath の mtime      ← 場所も OS が知っている

台帳を launchd から生やすと、**登録した瞬間に台帳に載る。**
「足したのに見られていない」が起こせなくなる。gateway の中で走る定時
（朝の便り・SNSの下書き）も同じで、契約と受領証は gateway の sqlite にある。

## runs の delta は使える（2026-09-12 実測）

覚え書きには「launchctl の runs は起点が不明なので判定に使えない」とある。
**それは絶対値の話で、差分は別。**60秒ごとの model-guard を2.5分見たら
4915→4916→4917→4918 と、**1回走るごとにちょうど1ずつ増えた。**
減ったら読み込み直し（それ自体が知らせる価値のある出来事）。

## 二重記録で嘘が見える

本人が書けるのは心拍だけなので、突き合わせると食い違いが出る。

    runs 増えた ＋ 心拍 新しい    → 生きている
    runs 増えた ＋ 心拍 古い      → **走ったのに走り切れていない**
                                    （今までどの見張りにも見えなかった形）
    runs 増えない ＋ 心拍 新しい  → **launchd を通らずに心拍が書かれた**
    期限を過ぎて runs 増えない    → 黙った
    exit != 0                     → 失敗している
    常駐なのに state != running   → 落ちている
    心拍はあるが契約が無い        → **誰も期限を決めていない**

最後の1つが肝で、**分からないものを黙って見送らない。**
この家で一番怖いのは止まることではなく黙ることなので、
**既定を「黙る」ではなく「鳴る」に倒してある。**

## 寝ている間は判定しない

寝ている Mac では誰も走れない。時計の差だけで測ると、起きた瞬間に全部が
「黙った」になる（2026-08-31 に見張り2人が23分殺し合った事故と同じ根）。
だからこちらは**自前の「起きていた時計」**を持つ。点呼と点呼の間隔が
300秒以内のときだけ足す。寝ていた時間は、どうやっても足せない。

## 完全ではない。どこまでかを書く

    この機械が動いていれば拾える … 上の7つ全部
    拾えない                      … 機械ごと落ちた／launchd ごと死んだ
                                    → **外の証人が要る。ここには無い。**

**外の証人が無いことを「たぶん大丈夫」で埋めない。**
`点呼()` は最後に必ず「外の証人: 無し」を返す。消したければ実際に置くこと。
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schedlib  # noqa: E402
from guardlib import env_value  # noqa: E402

HOME = os.path.expanduser("~")
OPENCLAW = os.path.join(HOME, ".openclaw")
PULSE_DIR = os.path.join(OPENCLAW, "pulse")
AGENTS = os.path.join(HOME, "Library", "LaunchAgents")
STATE_FILE = os.path.join(OPENCLAW, "silence-state.json")
CRON_DB = os.path.join(OPENCLAW, "state", "openclaw.sqlite")

# 契約がどこにも無い心拍について、人が一言だけ決める場所。
#
#   {"config-guard": {"呼ばれて走る": "watchdog と訓練が必要なときに呼ぶ"},
#    "house-brief":  {"間隔": 86400}}
#
# **既定は「鳴る」。**黙らせるにはここに1行書く。逆にしてはいけない
# ——既定を黙るほうにすると、誰も決めていないものが、決めたものと
# 同じ顔で並ぶ。この家が繰り返し踏んできたのはそれ。
# 使われなくなった宣言も鳴らす（消し忘れが黙って溜まると、
# ここ自体が「黙らせる装置」になる）。
宣言ファイル = os.path.join(OPENCLAW, "silence-contracts.json")


def 宣言():
    """人が決めた契約。**`_` で始まる鍵は書き置き**として読み飛ばす。

    JSON には注釈が書けない。外した宣言の理由を残す場所が無いと、
    次に読む人が「なぜ消したのか」を辿れなくなる。読み飛ばさないと
    書き置き自体が「使われていない宣言」として鳴る（2026-09-13 に踏んだ）。"""
    try:
        with open(宣言ファイル) as f:
            d = json.load(f)
        return {k: v for k, v in d.items()
                if not k.startswith("_")} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

# 点呼と点呼の間がこれより開いていたら、寝ていたと見なして起きていた時計に足さない。
# **足してしまうと、寝起きに家じゅうが「黙った」になる。**
起きていたと数える上限 = 300

# 期限からどれだけ遅れたら黙ったと呼ぶか。間隔の何倍か＋固定の余裕。
# 1.5倍なのは「1回飛ばした」を拾い、「たまたま重なった」を拾わないため。
遅れの許容 = 1.5
遅れの底上げ = 600

# 判定の名前。**ここを直すときは verify() の期待も一緒に直すこと。**
生 = "生きている"
黙 = "黙った"
半 = "走り切れていない"
失 = "失敗している"
落 = "落ちている"
外 = "定時を通っていない"
契約なし = "誰も期限を決めていない"
様子見 = "様子見"
測れず = "測れない"

# 知らせるべき判定。**様子見と生きているだけが、黙っていい。**
暴走 = "立ち上がっては落ちている"

# 知らせるべき判定。**様子見と生きているだけが、黙っていい。**
鳴る判定 = (黙, 半, 失, 落, 外, 契約なし, 測れず, 暴走)

# 1回の点呼のあいだに、契約より何倍速く起き直したら暴走と呼ぶか。
# **常駐は本来ほとんど起き直さない**ので、2回でも多い。
# 2026-09-06、更新に失敗した gateway が10秒おきに起動しては死に、
# Discord と LINE が同時に沈んだ。あのとき誰も「暴走している」とは言わなかった
# （見張りは「立っている／落ちている」を往復して見ていただけ）。
常駐の起き直しの上限 = 3
定時の速すぎ = 3.0


# ── 契約（launchd が持っている） ──────────────────────────

def _plist(path):
    """plist を dict で読む。**読めなければ None。空 dict を返さない。**

    空 dict を返すと「間隔の指定が無い常駐」に化けて、
    読めなかったことが健全に見える。"""
    try:
        r = subprocess.run(["plutil", "-convert", "json", "-o", "-", path],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _calendar_interval(spec):
    """StartCalendarInterval から「何秒ごとか」を出す。

    Hour と Minute があれば1日1回、Minute だけなら1時間に1回。
    **Weekday があれば1週間に1回**（backup が毎週になった日に、
    毎日の物差しで測ると毎回「黙った」になる）。"""
    specs = spec if isinstance(spec, list) else [spec]
    best = None
    for s in specs:
        if not isinstance(s, dict):
            continue
        if "Weekday" in s or "Month" in s:
            secs = 7 * 86400
        elif "Hour" in s:
            secs = 86400
        elif "Minute" in s:
            secs = 3600
        else:
            secs = 86400
        best = secs if best is None else min(best, secs)
    # 同じ時刻指定が複数あれば、その回数ぶん間隔は短い
    if best and len(specs) > 1:
        best = max(60, best // len(specs))
    return best


def _心拍名(label末尾, prog):
    """その仕事が心拍を書くなら、どの名前で書くか。

    **プログラム名から決めない。**`/bin/sh -c ...` で包んである仕事では
    「sh」になる（2026-09-12、証明が見つけた）。ラベルの末尾を先に見て、
    実際に心拍が置いてあるほうを採る。どちらも無ければラベルの末尾。"""
    候補 = [label末尾]
    if prog:
        候補.append(os.path.basename(prog))
    for n in 候補:
        if os.path.exists(os.path.join(PULSE_DIR, "%s.json" % n)):
            return n
    return label末尾


def launchd契約():
    """登録されている常駐・定時の仕事を、契約つきで全部返す。

    **仕組み（launchd / systemd / 無し）は schedlib が知っている。**
    ここは「心拍をどの名前で書くか」と「宣言」を足すだけにする
    （2026-09-23、Linux と Windows へ持っていくために窓口を分けた）。

    **登録されているものが全部。**置いてあっても読み込まれていなければ走らないので、
    ここには出さない（出すと「置いてあるから大丈夫」と読めてしまう）。"""
    決め = 宣言()
    out = {}
    for label, c in schedlib.一覧().items():
        名 = c.get("名前") or label.split(".")[-1]
        種 = c.get("種類")
        out[label] = {"名前": 名,
                      "種類": 測れず if 種 == schedlib.測れず else 種,
                      "間隔": c.get("間隔"), "元": c.get("元"),
                      "ログ": c.get("ログ"),
                      "心拍名": _心拍名(名, c.get("プログラム")),
                      "宣言": 決め.get(名)}
        if c.get("理由"):
            out[label]["理由"] = c["理由"]
    return out


def cron契約():
    """gateway の中で走る定時。契約も受領証も gateway の sqlite にある。

    **job 自身は sqlite を書かない**ので、ここも本人には書けない記録。
    nextRunAtMs は gateway が決めた期限そのもので、これを過ぎているのに
    lastRunAtMs が動いていなければ、**呼ぶ側が止まっている。**"""
    out = {}
    if not os.path.exists(CRON_DB):
        return out
    try:
        import sqlite3
        con = sqlite3.connect("file:%s?mode=ro" % CRON_DB, uri=True, timeout=3)
        rows = list(con.execute("select name, enabled, state_json from cron_jobs"))
        con.close()
    except Exception:
        return out
    for name, enabled, state_json in rows:
        if not enabled:
            continue
        try:
            st = json.loads(state_json or "{}")
        except ValueError:
            st = {}
        out["cron:" + name] = {
            "名前": name,
            "種類": "定時",
            "元": "cron",
            "次": (st.get("nextRunAtMs") or 0) / 1000.0 or None,
            "最後": (st.get("lastRunAtMs") or 0) / 1000.0 or None,
            "状態": st.get("lastRunStatus"),
            "心拍名": name,
        }
    return out


def 契約たち():
    """家じゅうの定期的なもの。**launchd と cron と、契約の無い心拍。**

    3つ目が肝。心拍だけあって契約がどこにも無いものは、
    **誰かが作って、誰も期限を決めなかった仕事**である。
    黙って見送ると、止まっても分からない。"""
    c = launchd契約()
    c.update(cron契約())
    決め = 宣言()
    載っている = {v.get("心拍名") for v in c.values()} | {v["名前"] for v in c.values()}
    try:
        for f in sorted(os.listdir(PULSE_DIR)):
            if not f.endswith(".json"):
                continue
            name = f[:-5]
            if name in 載っている:
                continue
            c["pulse:" + name] = {"名前": name, "種類": "契約なし", "間隔": None,
                                  "元": "心拍だけ", "心拍名": name,
                                  "宣言": 決め.get(name)}
    except OSError:
        pass
    # **使われなくなった宣言も名指しする。**消し忘れが溜まると、
    # このファイル自身が静かな「黙らせる装置」になる。
    使った = {v["名前"] for v in c.values()}
    for name in 決め:
        if name not in 使った:
            c["宣言:" + name] = {"名前": name, "種類": "宣言だけ", "元": "宣言だけ",
                                 "心拍名": name}
    return c


# ── 受領証（本人には書けない） ────────────────────────────

def 帳簿(label):
    """本人には書けない記録。**読めなければ None を返す。**
    0 や空を返すと、読めなかったことが「一度も走っていない」に化ける。
    中身は仕組みで違う（launchd は起き直しの回数、systemd は最後に走り出した時刻）。"""
    return schedlib.帳簿(label)


def 聴いている口():
    """いま LISTEN しているポートを {pid: {ポート}} で。読めなければ None。

    **一覧を手で書かない。**どのサービスがどのポートかは、元気なうちに
    実物から覚える（下の 常駐 の判定）。手で書くと、変えた日から嘘になる。
    1回で全部取れて実測 0.03 秒なので、仕事ごとに呼ばない。"""
    try:
        r = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    out = {}
    for row in r.stdout.splitlines()[1:]:
        c = row.split()
        if len(c) < 9:
            continue
        m = re.search(r":(\d+)$", c[8])
        if not m:
            continue
        try:
            out.setdefault(int(c[1]), set()).add(int(m.group(1)))
        except ValueError:
            pass
    return out


def 心拍時刻(name):
    """本人が書いた心拍の時刻。**これだけは本人が嘘をつける。**"""
    try:
        with open(os.path.join(PULSE_DIR, "%s.json" % name)) as f:
            return datetime.fromisoformat(json.load(f)["at"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ログ時刻(path):
    """plist が指しているログの最終更新。何も書かない仕事では動かない。"""
    try:
        return os.path.getmtime(os.path.expanduser(path))
    except (OSError, TypeError):
        return None


# ── 覚え書き ──────────────────────────────────────────────

def 読む覚え():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def 書く覚え(s):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


# ── 点呼 ──────────────────────────────────────────────────

def 点呼(いま=None, 覚え=None, 契約=None, 読む帳簿=None, 読む心拍=None, 読む口=None,
        自分=None):
    """家じゅうを1回読んで、(所見, 新しい覚え) を返す。

    `自分` … 点呼をしている当人の label。**自分の行だけは、いま走っている自分ではなく
    1つ前の走りと比べる。**当人は自分を見るとき必ず「走っている最中」なので、
    そのままだと自分の行が永久に据え置かれ、**自分の黙りは誰にも見えない**
    （2026-09-23 に判明。watchdog を見ているのは model-guard の相互心拍だけだった）。

    読む係を差し替えられるのは、**証明が本物の家を壊さずに済むようにするため**
    （guard-drill が偽ログで busy を試すのと同じ形）。
    差し替えなければ本物を読む。"""
    いま = time.time() if いま is None else いま
    覚え = 読む覚え() if 覚え is None else dict(覚え)
    契約 = 契約たち() if 契約 is None else 契約
    読む帳簿 = 読む帳簿 or 帳簿
    読む心拍 = 読む心拍 or 心拍時刻
    # **1回だけ読む。**仕事ごとに呼ぶと lsof を何度も起こす。
    口 = 聴いている口() if 読む口 is None else 読む口

    前 = 覚え.get("仕事", {})
    前回 = 覚え.get("いつ")
    覚えの時刻 = 前回
    # **起きていた時計。**点呼どうしの間が近いときだけ足す。
    足す = 0
    if 前回 is not None and 0 <= いま - 前回 <= 起きていたと数える上限:
        足す = いま - 前回

    所見, 新 = [], {}
    for key, c in sorted(契約.items()):
        古 = 前.get(key, {})
        起きていた = 古.get("起きていた", 0) + 足す
        rec = {"起きていた": 起きていた}
        判定, 説明 = _1件(key, c, 古, rec, いま, 読む帳簿, 読む心拍, 口, 覚えの時刻,
                        自分=(自分 is not None and key == 自分))
        rec["判定"] = 判定
        新[key] = rec
        所見.append({"名前": c.get("名前", key), "鍵": key, "元": c.get("元"),
                     "判定": 判定, "説明": 説明})

    # **外の証人は最後に必ず出す。**無いものを黙って無視しない。
    所見.append(dict(_外の証人(いま, 読む心拍), 鍵="外の証人", 元="外"))
    return 所見, {"いつ": いま, "仕事": 新}


def _外の証人(いま, 読む心拍, 確かめた=None, 押せた=None):
    """機械ごと落ちたときに気づく者が、外に居るか。

    **中から確かめられるのは「押せているか」まで。**外の見張りが生きているかは、
    外でしか分からない（中から確かめられるなら、それは外の証人ではない）。
    だから、ここは**押せているかだけを見て、確かめていないことは確かめていないと書く**。

    押す側 … `beacon`（launchd・15分ごと）が秘密 gist に時刻を置く
    見る側 … claude.ai の routine（1時間ごと・Anthropic のクラウド）"""
    名 = {"名前": "外の証人"}
    証人 = env_value("BEACON_WITNESS")
    gid = env_value("BEACON_GIST")
    if not gid or not 証人:
        return dict(名, 判定=測れず,
                    説明="機械ごと落ちたときに気づく者が居ない（この家の外に無い）")
    # **心拍ではなく「押せた跡」を見る。**
    # 心拍は `Guard.run` が必ず書くので、**押せなくても新しくなる**。
    # 2026-09-14、外の印が1時間39分止まっているのに、ここは「押せている」と言った。
    # しかも `beacon --show` で確かめるたびに心拍が更新され、**確かめる行為が
    # 古さを隠していた。**本人の自己申告を、結果として読んではいけない。
    if 押せた is not None:
        心 = 押せた or None
    else:
        try:
            with open(os.path.join(OPENCLAW, "beacon-pushed.json")) as f:
                心 = datetime.fromisoformat(json.load(f)["at"]).timestamp()
        except (OSError, ValueError, KeyError, TypeError):
            心 = None
    if 心 is None:
        return dict(名, 判定=黙,
                    説明="外に一度も押せていない（beacon-pushed.json が無い）")
    遅れ = いま - 心
    # beacon は15分ごと。**押せていなければ、外からは「機械が死んだ」に見える。**
    if 遅れ > 900 * 遅れの許容 + 遅れの底上げ:
        return dict(名, 判定=黙,
                    説明="外に %s 押せていない（外からは機械が落ちたように見える）"
                          % _長さ(遅れ))

    # **押せていることは、外から読めていることの証拠ではない。**
    # 2026-09-13、外の定時は登録できているのに gist に届かなかった
    # （クラウドの砂場から curl が出られない。git clone なら通った）。
    # **通ることを一度は実際に見せる**——見せた日を残し、古くなったら鳴らす。
    # 壁は黙って壁でなくなるので、「前に通った」は今日の証拠にならない。
    # **差し替え口。**`env_value` は空文字だとファイルへ落ちるので、
    # 環境変数を空にしても「無い」を作れない（訓練がそこで空振りした）。
    if 確かめた is None:
        確かめた = env_value("BEACON_WITNESS_OK")
    if not 確かめた:
        return dict(名, 判定=測れず,
                    説明="押せてはいるが、**外から読めることをまだ一度も見せていない**"
                          "（BEACON_WITNESS_OK が無い）")
    try:
        日 = datetime.fromisoformat(確かめた)
        古さ = (datetime.now() - 日).total_seconds()
    except (ValueError, TypeError):
        return dict(名, 判定=測れず,
                    説明="BEACON_WITNESS_OK が日付として読めない（%s）" % 確かめた)
    if 古さ > 30 * 86400:
        return dict(名, 判定=測れず,
                    説明="外から読めることを確かめたのが %s前。"
                          "壁は黙って壊れるので、もう一度通してから数えること"
                          % _長さ(古さ))
    return dict(名, 判定=生,
                説明="%s前に外へ押した。読む側は外の定時（%s・1時間ごと）で、"
                      "そこから実際に読めることを %s に見せてある"
                      % (_長さ(遅れ), 証人, 確かめた))


def _1件(key, c, 古, rec, いま, 読む帳簿, 読む心拍, 口=None, 覚えの時刻=None,
         自分=False):
    """1本ぶんの判定。**rec は書き足して返す（次回の突き合わせに使う）。**"""
    元 = c.get("元")

    if 元 == "宣言だけ":
        return 契約なし, ("%s に書いてあるが、その名前の仕事も心拍も無い"
                          "（消し忘れ）" % os.path.basename(宣言ファイル))

    if 元 == "心拍だけ":
        t = 読む心拍(c["心拍名"])
        古さ = "（最後は %s）" % _いつ(t, いま) if t else ""
        決め = c.get("宣言") or {}
        if "呼ばれて走る" in 決め:
            return 生, "手で呼ぶものと決めてある（%s）%s" % (決め["呼ばれて走る"], 古さ)
        if 決め.get("間隔"):
            間隔 = float(決め["間隔"])
            if t is None:
                return 黙, "%s ごとと決めてあるが、心拍が一度も無い" % _長さ(間隔)
            遅れ = いま - t
            if 遅れ > 間隔 * 遅れの許容 + 遅れの底上げ:
                return 黙, "%s ごとと決めてあるのに %s" % (_長さ(間隔), _いつ(t, いま))
            return 生, "%s ごと・最後は %s" % (_長さ(間隔), _いつ(t, いま))
        return 契約なし, ("心拍はあるが、どこにも期限が書かれていない%s"
                          "／決めるには %s に1行" % (古さ, os.path.basename(宣言ファイル)))

    if 元 == "cron":
        return _cron判定(c, いま)

    b = 読む帳簿(key)
    if b is None or (b.get("runs") is None and b.get("走り出した") is None):
        return 測れず, "帳簿が読めない（%s）" % (schedlib.仕組み() or "仕組みが無い")
    if 自分:
        # **いま走っているのは、この点呼そのもの。**その1回を数から外して、
        # 1つ前の走りを見る（心拍も前の走りが書いたものが残っている）。
        # こうしないと「回数は増えたのに心拍が古い」で毎回引っかかる。
        b = dict(b)
        if b.get("runs"):
            b["runs"] -= 1
        elif b.get("走り出した"):
            # 回数を数えられない仕組みでは、いまの走り出しを「前の走り」に見せる
            b["走り出した"] = (古.get("走り出した") or b["走り出した"])
        b["state"], b["pid"] = "not running", None
    rec["runs"] = b.get("runs")
    rec["走り出した"] = b.get("走り出した")
    # **回数を見た時刻も一緒に残す。**据え置いた回数を、進み続ける時計と
    # 比べると、据え置かれているあいだに増えたぶんが「1回の点呼で増えた」に化ける
    # （2026-09-23、watchdog が4分ごとに「立ち上がっては落ちている」と鳴った）。
    rec["runs時刻"] = いま
    rec["exit"] = b["exit"]

    心 = 読む心拍(c.get("心拍名") or c.get("名前"))
    rec["心拍"] = 心

    if c["種類"] == "常駐":
        # **起き直しが速すぎないか。**KeepAlive は落ちるたびに起こすので、
        # 起動直後に落ちる状態だと、立っているように見えたまま永久に回る
        # （中途半端に書き換わった設定やファイルが残っていると、この形になる）。
        前runs = 古.get("runs")
        if (前runs is not None and b.get("runs") is not None
                and b["runs"] - 前runs >= 常駐の起き直しの上限):
            return 暴走, ("この1回の点呼のあいだに %d 回起き直した"
                          "（常駐は本来ほとんど起き直さない）。"
                          "**起動直後に落ちている疑い**——中途半端に残った"
                          "ファイルや設定を先に見ること" % (b["runs"] - 前runs))

        # **ポートを掴んだまま残る孤児を見る。**
        #
        # 親を SIGKILL しても、サブシェルで起こした子や孫はポートを掴んだまま
        # 生き残る。launchd が起こし直しても `EADDRINUSE` で即死するので、
        # **「立っていない」と「立てない」が区別できないと、蹴り続けるだけになる。**
        #
        # どのサービスがどのポートかは**元気なうちに実物から覚える**。
        # 手で一覧を書くと、ポートを変えた日から嘘になる。
        覚えた = set(古.get("ポート") or [])
        if b.get("state") == "running" and b.get("pid"):
            いまの口 = (口 or {}).get(b["pid"], set())
            rec["ポート"] = sorted(覚えた | set(いまの口))
            # 覚えた口を、別のものが掴んでいないか（乗っ取られた形）
            余所 = {p for p in 覚えた if p not in いまの口
                    and any(p in v for k, v in (口 or {}).items() if k != b["pid"])}
            if 余所 and 口 is not None:
                return 外, ("立ってはいるが、覚えた口 %s を別のプロセスが掴んでいる"
                            % sorted(余所))
            return 生, ("立っている（pid %s・口 %s）" % (b["pid"], sorted(いまの口))
                        if いまの口 else "立っている（pid %s）" % b["pid"])
        rec["ポート"] = sorted(覚えた)
        if 覚えた and 口 is not None:
            掴まれている = {p: k for p in 覚えた
                            for k, v in 口.items() if p in v}
            if 掴まれている:
                return 落, ("落ちているのに、口 %s を別のプロセス（pid %s）が"
                            "掴んでいる。**起こし直しても EADDRINUSE で即死する**"
                            % (sorted(掴まれている), sorted(set(掴まれている.values()))))
        return 落, "常駐のはずが state=%s" % (b.get("state") or "不明")

    # ── ここから定時 ──
    前runs, 前心 = 古.get("runs"), 古.get("心拍")
    前走 = 古.get("走り出した")
    # **回数を数えられる仕組み（launchd）と、数えられない仕組み（systemd）がある。**
    # 数えられないほうは「最後に走り出した時刻が進んだか」で見る。
    # 0 で埋めて数えたふりをしない（数えられない、と回数が0は別物）。
    if b.get("runs") is not None:
        走った = 前runs is not None and b["runs"] > 前runs
        戻った = 前runs is not None and b["runs"] < 前runs
    else:
        # **時刻は絶対値なので、前の回を知らなくても「前の点呼より後に走った」は言える。**
        # 回数（launchd）は起点が分からないので初回は判断できないが、こちらは分かる
        # （2026-09-23、Linux の実物で「初めて見た」に落ちていたのを直した）。
        走 = b.get("走り出した")
        走った = (走 is not None
                and ((前走 is not None and 走 > 前走 + 0.05)
                     or (前走 is None and 覚えの時刻 is not None and 走 > 覚えの時刻)))
        戻った = False

    # **契約より速すぎないか。先に見る。**
    # 1回の点呼のあいだに、間隔から見て起こりうる回数の3倍を超えて走っていたら、
    # 落ちては起き直している。**走っている最中の見送りより前に置くこと**——
    # 暴走している仕事はたいてい「いま走っている」ので、後ろに置くと
    # 見送りに吸われて永久に見えない（2026-09-14、実際にそうなった）。
    if 走った:
        間 = c.get("間隔") or 0
        # **前の回数を見た時刻から測る。**点呼の時刻から測ると、据え置き
        # （走っている最中）のあいだ回数だけが溜まり、溜まったぶんを1回ぶんとして
        # 割ることになる。点呼をしている当人（watchdog）は自分を見るとき必ず
        # 「走っている最中」なので、**自分だけが4分ごとに暴走に見えていた**。
        経過 = max(1.0, いま - (古.get("runs時刻") or 覚えの時刻 or いま))
        起こりうる = max(1.0, 経過 / 間) if 間 else 1.0
        増えた = (b["runs"] - 前runs) if b.get("runs") is not None else None
        if 間 and 増えた is not None and 増えた > 起こりうる * 定時の速すぎ:
            return 暴走, ("%s ごとのはずが、%s のあいだに %d 回走った"
                          "（起こりうるのは %.0f 回まで）。"
                          "**走り出してすぐ落ちている疑い**——中途半端に残った"
                          "ファイルや設定を先に見ること"
                          % (_長さ(間), _長さ(経過), 増えた, 起こりうる))

    # **走っている最中は判定しない（2026-09-13 に直した）。**
    #
    # launchd は仕事を起こした時点で runs を上げる。心拍は仕事が走り切った
    # あとに本人が書く。**その隙間に点呼が来ると、「回数は増えたのに心拍が古い」
    # ＝走り切れていない、に見える。**実際には走っている最中でしかない。
    #
    # 実測: この誤報を1日で **120回** 出した（model-guard 52・watchdog 17・
    # loop-guard 13 …）。しかも鳴るたびに「全部戻った」と往復するので、
    # 変わったときだけ知らせる作りが**毎回「変わった」と読む**。
    # 知らせは261行になった。**この家でいちばん避けたい「読まれない警報」。**
    #
    # 帳簿の回数も心拍も**据え置く**こと。ここで回数だけ進めると、
    # 走り切れずに消えた回を次の点呼が見逃す（直したつもりで穴を開ける）。
    走っている = b.get("state") == "running" or b.get("pid")
    if 走っている and rec["起きていた"] <= (c.get("間隔") or 0) * 遅れの許容 + 遅れの底上げ:
        rec["runs"] = 前runs if 前runs is not None else b.get("runs")
        rec["走り出した"] = 前走 if 前走 is not None else b.get("走り出した")
        # 回数を据え置くなら、その回数を見た時刻も据え置く（上の経過と対で効く）
        rec["runs時刻"] = 古.get("runs時刻") or 覚えの時刻 or いま
        rec["心拍"] = 前心 if 前心 is not None else 心
        return 様子見, "走っている最中（終わってから見る）"

    if 走った:
        rec["起きていた"] = 0          # 走ったので、遅れの時計は振り出しに戻る
        rec["最後に走った"] = いま

    # **0 以外で終わったことを、毎回は鳴らさない。**
    # この家の見張りは「困りごとを見つけた」を exit 1 で返す（watchdog も
    # そうなっている）。走るたびに鳴らすと、**見張りが仕事をした跡を
    # 故障として数え続ける**ことになり、2026-09-12 に実際にそうなった。
    # 見るのは **走った瞬間だけ**、しかも **走り切ったかと突き合わせて**。
    走り切った = 心 is not None and 前心 is not None and 心 > 前心
    if 走った and b.get("exit") not in (0, None):
        if not 走り切った and 心 is not None:
            return 失, ("exit %s で終わり、心拍も残していない"
                        "（走り切る前に消えている）" % b["exit"])
        return 生, "走った（exit %s・知らせることがあった）" % b["exit"]
    if 前runs is None and b.get("exit") not in (0, None):
        # 初めて見たときは走った瞬間が分からない。**それでも黙らない。**
        return 失, ("最後に走ったとき exit %s で終わっている"
                    "（いつのことかは、次の点呼から数える）" % b["exit"])

    if 走った and 心 is not None and 前心 is not None and 心 <= 前心:
        return 半, ("launchd は走らせたのに心拍が更新されていない"
                    "（走って、走り切る前に消えている）")
    if 走った and 心 is None:
        # 心拍を残さない仕事は7本ある。**残していない仕事に残せとは言わない。**
        return 生, "走った（runs %s→%s・心拍は元から無い）" % (前runs, b["runs"])
    if 戻った:
        return 様子見, "帳簿の回数が %s→%s と戻った（読み込み直し）" % (前runs, b["runs"])

    if c["種類"] == "期限なし":
        return 契約なし, "plist に間隔も時刻も KeepAlive も書かれていない"
    if c["種類"] == 測れず:
        return 測れず, c.get("理由", "契約が読めない")

    間隔 = c.get("間隔") or 0
    許容 = 間隔 * 遅れの許容 + 遅れの底上げ
    if rec["起きていた"] > 許容:
        # **ここが、この道具でいちばん効く一行。**
        #
        # 期限を過ぎても launchd は走らせていない。それなのに心拍だけが
        # 新しいなら、**心拍を見ている見張りからは元気に見えている。**
        # この家の見張りは全員 pulse_age() で生死を判断しているので、
        # この形は**原理的に誰にも見えない**。手で走らせ続けているあいだ、
        # 定時が死んでいることに誰も気づかない、がそれ。
        #
        # 回数で数えるのはやめた（2026-09-12）。手で2回続けて走らせただけで
        # 鳴った。**人が触った回数は、嘘とは関係が無い。**期限で見る。
        if 心 is not None and (いま - 心) < 許容:
            return 外, ("%s ごとのはずが、起きている時間で %s launchd が"
                        "走らせていない。なのに心拍だけ新しい（%s）"
                        "——心拍を見ている見張りからは元気に見えている"
                        % (_長さ(間隔), _長さ(rec["起きていた"]), _いつ(心, いま)))
        return 黙, ("%s ごとのはずが、起きている時間で %s 走っていない"
                    % (_長さ(間隔), _長さ(rec["起きていた"])))
    if 走った:
        return 生, ("走った（runs %s→%s）" % (前runs, b.get("runs"))
                   if b.get("runs") is not None else "走った（走り出した時刻が進んだ）")
    if 前runs is None and 前走 is None:
        return 様子見, "初めて見た（次の点呼から数え始める）"
    return 生, "%s ごと・遅れ %s" % (_長さ(間隔), _長さ(rec["起きていた"]))


def _cron判定(c, いま):
    """gateway の定時。**期限は gateway が書いた nextRunAtMs。**"""
    次, 最後, 状態 = c.get("次"), c.get("最後"), c.get("状態")
    if 次 is None:
        return 測れず, "gateway が次の予定を書いていない"
    遅れ = いま - 次
    if 遅れ > 遅れの底上げ:
        return 黙, ("%s に走る予定が %s 過ぎても動いていない（呼ぶ側が止まっている）"
                    % (datetime.fromtimestamp(次).strftime("%m-%d %H:%M"), _長さ(遅れ)))
    if 状態 and 状態 not in ("ok", "skipped"):
        return 失, "前回 %s（%s）" % (状態, _いつ(最後, いま))
    return 生, "次は %s" % datetime.fromtimestamp(次).strftime("%m-%d %H:%M")


def _長さ(s):
    s = int(s or 0)
    if s < 90:
        return "%d秒" % s
    if s < 5400:
        return "%d分" % (s // 60)
    if s < 2 * 86400:
        return "%d時間" % (s // 3600)
    return "%d日" % (s // 86400)


def _いつ(t, いま):
    return "%s前" % _長さ(いま - t) if t else "一度も"


# ── 証明 ──────────────────────────────────────────────────

PROBE_LABEL = "ai.openclaw.silence-probe"
PROBE_PLIST = os.path.join(OPENCLAW, "silence-probe.plist")
PROBE_MODE = os.path.join(OPENCLAW, "silence-probe-mode")
PROBE_PULSE = os.path.join(PULSE_DIR, "silence-probe.json")

PROBE_SH = r'''
m=$(cat "%s" 2>/dev/null || echo ok)
case "$m" in
  fail) exit 3 ;;
  mute) exit 0 ;;
  *) printf '{"at": "%%s"}' "$(date +%%Y-%%m-%%dT%%H:%%M:%%S)" > "%s" ; exit 0 ;;
esac
''' % (PROBE_MODE, PROBE_PULSE)


def _probe_install():
    """使い捨ての仕事を、**本物の仕組みに**登録する（launchd でも systemd でも）。

    登録できない機械（仕組みが無い・権限が無い）では False。**そのときは
    「測れない」と言うこと**——ここで嘘の合格を作らない。
    走らせるのはこちらから1回ずつなので、間隔は長くしておく。"""
    import schedlib
    os.makedirs(PULSE_DIR, exist_ok=True)
    return schedlib.使い捨て登録(PROBE_LABEL, PROBE_SH, 間隔=86400,
                             plist置き場=PROBE_PLIST)


def _probe_remove():
    import schedlib
    schedlib.使い捨て削除(PROBE_LABEL, plist置き場=PROBE_PLIST)
    for p in (PROBE_PLIST, PROBE_MODE, PROBE_PULSE):
        try:
            os.unlink(p)
        except OSError:
            pass


def _probe_run(mode, timeout=30):
    """使い捨ての仕事を1回走らせて、**終わるまで**待つ。

    **`state != "running"` で待つと待てていない。**launchd は
    spawn scheduled → xpcproxy → running → not running と移る。
    2026-09-12、`!= "running"` で見たら xpcproxy の段階で先へ進み、
    心拍がまだ書かれていない帳簿を読んで「心拍を残さない仕事」に化けた。
    **回数が増えて、かつ not running になるまで**待つ。"""
    import schedlib
    前 = 帳簿(PROBE_LABEL) or {}
    前runs = 前.get("runs")
    前走 = 前.get("走り出した")
    with open(PROBE_MODE, "w") as f:
        f.write(mode)
    schedlib.一度走らせる(PROBE_LABEL)
    end = time.time() + timeout
    while time.time() < end:
        b = 帳簿(PROBE_LABEL)
        if b and b.get("state") == "not running" and b.get("pid") is None:
            # 回数が数えられる仕組みなら回数で、数えられないなら走り出した時刻で見る
            if 前runs is not None and b.get("runs") is not None:
                if b["runs"] > 前runs:
                    return b
            elif b.get("走り出した") is not None and (
                    前走 is None or b["走り出した"] > 前走 + 0.5):
                return b
        time.sleep(0.2)
    return 帳簿(PROBE_LABEL)


def verify():
    """**この機械で、黙りが本当に見えるか。**使い捨ての仕事を実際に走らせて確かめる。

    どの項目にも「通るべき側」を入れてある。全部を鳴らすように壊れたとき、
    それを合格と読み違えないため（guardrun.verify() と同じ作法）。

    返すのは {項目: (効いたか, 説明)}。**測れなかったものは False。**"""
    out = {}
    # **「本物の仕事の記録が読めるか」は、その機械に居る仕事で見る。**
    # 決め打ちすると、家がまだ無い機械（新しく入れた Linux など）では
    # 「読めない」に化ける——読めないのは仕組みではなく、その仕事が居ないだけ。
    健全な本物 = None
    for label, c in sorted(契約たち().items()):
        if label != PROBE_LABEL and c.get("種類") in ("定時", "常駐"):
            健全な本物 = label
            break

    if not _probe_install():
        for k in ("帳簿", "走った跡", "失敗", "走り切れていない",
                  "launchd を通らない心拍", "黙り", "台帳", "対照"):
            out[k] = (False, "使い捨ての仕事を登録できなかった")
        return out
    try:
        # ── 台帳: 登録した瞬間に載るか / 外した瞬間に消えるか ──
        c = 契約たち()
        載った = PROBE_LABEL in c
        out["台帳"] = (載った,
                       "登録しただけで台帳に載った（手で書き足していない）" if 載った
                       else "launchd に居るのに台帳に出てこない")

        # ── 帳簿が読めるか（本物で） ──
        b0 = 帳簿(健全な本物) if 健全な本物 else 帳簿(PROBE_LABEL)
        # **一度も走っていない仕事でも、状態は読める。**「読めない」と
        # 「まだ走っていない」を混ぜない（2026-09-23、Linux で混ざった）。
        よめた = bool(b0 and (b0.get("runs") is not None
                           or b0.get("走り出した") is not None
                           or b0.get("state")))
        out["帳簿"] = (よめた,
                       "%s の記録が読めた（runs=%s / 走り出した=%s / exit=%s）"
                       % (健全な本物 or "使い捨ての仕事", (b0 or {}).get("runs"),
                          _いつ(b0["走り出した"], time.time())
                          if (b0 or {}).get("走り出した") else None,
                          (b0 or {}).get("exit"))
                       if よめた else "本人には書けない記録が読めない（%s）"
                                      % (健全な本物 or "使い捨ての仕事"))

        # ── 走った跡: 1回走らせて runs がちょうど 1 増えるか ──
        前 = 帳簿(PROBE_LABEL)
        b = _probe_run("ok")
        if 前.get("runs") is not None and b and b.get("runs") is not None:
            増 = b["runs"] - (前["runs"] or 0)
            out["走った跡"] = (増 == 1,
                              "1回走らせて runs が %s→%s（ちょうど1）"
                              % (前["runs"], b["runs"]) if 増 == 1
                              else "1回走らせて runs の増えかたが %s" % 増)
        else:
            # **回数を数えられない仕組み（systemd）では、走り出した時刻で見る。**
            進んだ = bool(b and b.get("走り出した") is not None
                        and (前.get("走り出した") is None
                             or b["走り出した"] > 前["走り出した"] + 0.5))
            out["走った跡"] = (進んだ,
                              "1回走らせて走り出した時刻が進んだ（回数はこの仕組みでは数えられない）"
                              if 進んだ else "1回走らせても走り出した時刻が進まない")

        # ── 対照（通るべき側）: 健全な回は「生きている」と読むか ──
        覚え = {"いつ": time.time() - 10, "仕事": {PROBE_LABEL: {
            "runs": 前.get("runs"), "走り出した": 前.get("走り出した"),
            "心拍": 0, "起きていた": 0}}}
        所見, _ = 点呼(覚え=覚え, 契約={PROBE_LABEL: c.get(PROBE_LABEL)})
        判 = _ひく(所見, PROBE_LABEL)
        out["対照"] = (判 and 判["判定"] == 生,
                       "走って心拍も残した回は「%s」と読んだ" % (判 or {}).get("判定")
                       if 判 and 判["判定"] == 生
                       else "健全な回を「%s」と読んだ（何でも鳴る側に壊れている）"
                            % (判 or {}).get("判定"))

        # ── 失敗: exit 3 が見えるか ──
        前 = 帳簿(PROBE_LABEL)
        b = _probe_run("fail")
        覚え = {"いつ": time.time() - 10, "仕事": {PROBE_LABEL: {
            "runs": 前.get("runs"), "走り出した": 前.get("走り出した"),
            "心拍": 心拍時刻("silence-probe"), "起きていた": 0}}}
        所見, _ = 点呼(覚え=覚え, 契約={PROBE_LABEL: c.get(PROBE_LABEL)})
        判 = _ひく(所見, PROBE_LABEL)
        ok = bool(b and b.get("exit") == 3 and 判 and 判["判定"] == 失)
        out["失敗"] = (ok, "exit 3 で終わった回を「%s」と読んだ" % (判 or {}).get("判定")
                       if ok else "exit=%s を「%s」と読んだ"
                                  % ((b or {}).get("exit"), (判 or {}).get("判定")))

        # ── 走り切れていない: 走ったのに心拍が古い ──
        前心 = 心拍時刻("silence-probe")
        前 = 帳簿(PROBE_LABEL)
        b = _probe_run("mute")          # 走るが心拍を残さない
        覚え = {"いつ": time.time() - 10, "仕事": {PROBE_LABEL: {
            "runs": 前.get("runs"), "走り出した": 前.get("走り出した"),
            "心拍": 前心, "起きていた": 0}}}
        所見, _ = 点呼(覚え=覚え, 契約={PROBE_LABEL: c.get(PROBE_LABEL)})
        判 = _ひく(所見, PROBE_LABEL)
        ok = bool(判 and 判["判定"] == 半)
        out["走り切れていない"] = (ok,
            "走ったのに心拍を残さない回を「%s」と読んだ" % 判["判定"] if ok
            else "走ったのに心拍が古い回を「%s」と読んだ" % (判 or {}).get("判定"))

        # ── 走っている最中は判定しない ──
        # **通るべき側と、見逃していない側の両方を見る。**
        # 「走っている最中」を口実に何も言わなくなると、
        # 走り切れずに消えた回まで黙って通る。
        契r = dict(c.get(PROBE_LABEL))
        契r["間隔"] = 60
        古心 = time.time() - 3600
        覚r = {"いつ": time.time() - 10,
               "仕事": {PROBE_LABEL: {"runs": 10, "心拍": 古心, "起きていた": 0}}}

        def _帳簿(state, pid):
            return lambda k: {"runs": 11, "exit": 0, "state": state, "pid": pid,
                              "path": None}
        所r, 新r = 点呼(覚え=覚r, 契約={PROBE_LABEL: 契r},
                        読む帳簿=_帳簿("running", 999), 読む心拍=lambda n: 古心)
        走行中 = _ひく(所r, PROBE_LABEL)
        据え置き = 新r["仕事"][PROBE_LABEL].get("runs")
        所e, _ = 点呼(覚え=覚r, 契約={PROBE_LABEL: 契r},
                      読む帳簿=_帳簿("not running", None), 読む心拍=lambda n: 古心)
        終了後 = _ひく(所e, PROBE_LABEL)
        ok = bool(走行中 and 走行中["判定"] == 様子見
                  and 据え置き == 10
                  and 終了後 and 終了後["判定"] == 半)
        out["走っている最中は見ない"] = (ok,
            "走っている間は「%s」で据え置き、終わってから「%s」と読んだ"
            % (走行中["判定"], 終了後["判定"]) if ok
            else "走行中=%s（回数の据え置き=%s・10のはず）／終了後=%s（%s のはず）"
                 % ((走行中 or {}).get("判定"), 据え置き,
                    (終了後 or {}).get("判定"), 半))

        # ── 自分自身を見る ──
        # **点呼をしているのは当人なので、自分の行は必ず「走っている最中」に見える。**
        # 据え置いたままだと、自分が黙っても自分では言えない（2026-09-23 まで、
        # watchdog を見ているのは model-guard の相互心拍だけだった）。
        # 自分の行だけ「1つ前の走り」と比べる。**通るべき側（前の走りが元気）と
        # 見逃していない側（前の走りが心拍を残さず死んだ）の両方を見る。**
        契自 = dict(c.get(PROBE_LABEL)); 契自["間隔"] = 60
        def _自(心, 自分あり, 起きていた=0):
            覚自 = {"いつ": time.time() - 60,
                   "仕事": {PROBE_LABEL: {"runs": 10, "runs時刻": time.time() - 60,
                                        "心拍": 心, "起きていた": 起きていた,
                                        "ポート": []}}}
            帳自 = lambda k: {"runs": 11, "exit": 0, "state": "running",
                             "pid": 1, "path": None}
            所, _ = 点呼(いま=time.time(), 覚え=覚自, 契約={PROBE_LABEL: 契自},
                       読む帳簿=帳自, 読む心拍=lambda n: 心, 読む口={1: set()},
                       自分=(PROBE_LABEL if 自分あり else None))
            return _ひく(所, PROBE_LABEL)
        # **黙りは「起きているのに走っていない時間」で見る**（心拍の古さではない）。
        # 60秒ごとの仕事なら許容は 60×1.5+600＝690秒。そこを超えた形を作る。
        自元気 = _自(time.time() - 30, True)                      # 1つ前の走りは元気
        自黙り = _自(time.time() - 3600, True, 起きていた=3600)     # 11分以上走っていない
        # 他人の行は今までどおり据え置く（据え置きが効く条件＝走りっぱなしが長すぎない）。
        # ここを長くすると据え置きは外れる。それは正しい挙動なので、条件を分けて見る。
        他 = _自(time.time() - 3600, False)
        ok = (自元気 and 自元気["判定"] == 生
              and 自黙り and 自黙り["判定"] in (黙, 半)
              and 他 and 他["判定"] == 様子見)
        out["自分自身を見る"] = (bool(ok),
            "自分の行は1つ前の走りで見た（元気なら生きている・心拍を残さず死んだ回は %s）。"
            "他人の行は今までどおり据え置いた" % (自黙り or {}).get("判定") if ok
            else "自分（元気）=%s（生きているはず）／自分（黙り）=%s（%s か %s のはず）／他人=%s（%s のはず）"
                 % ((自元気 or {}).get("判定"), (自黙り or {}).get("判定"), 黙, 半,
                    (他 or {}).get("判定"), 様子見))

        # ── 立ち上がっては落ちている（暴走） ──
        # **中途半端に残ったファイルや設定があると、起き直すたびに即死する。**
        # 2026-09-06、更新に失敗した gateway が10秒おきに起動しては死んだ。
        # そのとき見張りは「立っている／落ちている」を往復して見ていただけで、
        # **暴走しているとは誰も言わなかった。**
        暴常 = {"名前": "暴走の試験", "種類": "常駐", "元": "launchd", "心拍名": "x"}
        暴定 = {"名前": "暴走の試験", "種類": "定時", "間隔": 60,
                "元": "launchd", "心拍名": "x"}
        def _帳(runs, 走行中=True):
            # **対照は「走り終わった」帳簿にすること。**走っている最中の帳簿を
            # 対照に使うと、見送り（様子見）が返って「生きている」にならない
            # ——判定ではなく試験のほうが間違う（2026-09-14 に踏んだ）。
            return lambda k: {"runs": runs, "exit": 0,
                              "state": "running" if 走行中 else "not running",
                              "pid": 1 if 走行中 else None, "path": None}
        def _見(契, runs, 前runs, 経過=60, 走行中=True, runs時刻ずれ=None):
            仕 = {"runs": 前runs, "心拍": None, "起きていた": 0, "ポート": []}
            if runs時刻ずれ is not None:
                仕["runs時刻"] = time.time() - runs時刻ずれ
            覚 = {"いつ": time.time() - 経過, "仕事": {"F": 仕}}
            return _ひく(点呼(いま=time.time(), 覚え=覚, 契約={"F": 契},
                             読む帳簿=_帳(runs, 走行中), 読む心拍=lambda n: None,
                             読む口={1: set()})[0], "F")
        常暴 = _見(暴常, 13, 10)      # 1分で3回起き直した
        常並 = _見(暴常, 11, 10)      # 1回だけ（入れ直しはふつうにある）
        定暴 = _見(暴定, 15, 10)      # 60秒ごとの仕事が60秒で5回
        定並 = _見(暴定, 11, 10, 走行中=False)   # 60秒で1回・走り終わっている
        # **据え置いた回数を、進み続ける時計と比べない。**（2026-09-23）
        # 点呼をしている当人（watchdog）は、自分を見るとき必ず「走っている最中」なので
        # 自分の回数だけが据え置かれる。時計だけ進めて比べると、溜まったぶんが
        # 「この1分で増えた」に化けて、**4分ごとに自分を暴走と呼んでいた**（実測）。
        据置 = _見(暴定, 3292, 3288, runs時刻ずれ=240)      # 4分ぶん据え置かれていた
        本物 = _見(暴定, 30, 10, runs時刻ずれ=60, 走行中=False)   # 1分で20回＝本物
        ok = (常暴 and 常暴["判定"] == 暴走 and 常並 and 常並["判定"] == 生
              and 定暴 and 定暴["判定"] == 暴走 and 定並 and 定並["判定"] == 生
              and 据置 and 据置["判定"] != 暴走 and 本物 and 本物["判定"] == 暴走)
        out["立ち上がっては落ちている"] = (bool(ok),
            "常駐が1分で3回・定時が契約の5倍で起き直したら鳴り、"
            "1回だけの入れ直しでは鳴らず、据え置き4分ぶんの溜まりも鳴らなかった" if ok
            else "常駐 暴走=%s 平常=%s ／ 定時 暴走=%s 平常=%s ／ 据え置き=%s（暴走でないはず） 本物=%s"
                 % ((常暴 or {}).get("判定"), (常並 or {}).get("判定"),
                    (定暴 or {}).get("判定"), (定並 or {}).get("判定"),
                    (据置 or {}).get("判定"), (本物 or {}).get("判定")))

        # ── 孤児がポートを掴んでいる ──
        # **「立っていない」と「立てない」は別物。**親を殺しても子や孫は
        # ポートを掴んだまま残り、起こし直しても EADDRINUSE で即死する。
        # 蹴るだけの見張りは、そこで永久に蹴り続ける。
        常 = {"名前": "常駐の試験", "種類": "常駐", "元": "launchd", "心拍名": "x"}
        def _常(state, pid):
            return lambda k: {"runs": 1, "exit": 0, "state": state, "pid": pid,
                              "path": None}
        覚え常 = lambda ポート: {"いつ": time.time() - 10, "仕事": {
            "L": {"ポート": ポート, "runs": 1, "心拍": None, "起きていた": 0}}}
        # 通るべき側: 立っていて、自分で掴んでいる
        所, 新 = 点呼(覚え=覚え常([]), 契約={"L": 常},
                      読む帳簿=_常("running", 111), 読む心拍=lambda n: None,
                      読む口={111: {8080}})
        健全 = _ひく(所, "L")
        覚えた = 新["仕事"]["L"].get("ポート")
        # 落ちていて、口は空いている → ただの「落ちている」
        所2, _ = 点呼(覚え=覚え常([8080]), 契約={"L": 常},
                      読む帳簿=_常("not running", None), 読む心拍=lambda n: None,
                      読む口={})
        ただ落ち = _ひく(所2, "L")
        # 落ちていて、別のプロセスが掴んでいる → 起こしても即死する
        所3, _ = 点呼(覚え=覚え常([8080]), 契約={"L": 常},
                      読む帳簿=_常("not running", None), 読む心拍=lambda n: None,
                      読む口={999: {8080}})
        孤児 = _ひく(所3, "L")
        ok = (健全 and 健全["判定"] == 生 and 覚えた == [8080]
              and ただ落ち and ただ落ち["判定"] == 落
              and 孤児 and 孤児["判定"] == 落
              and "EADDRINUSE" in 孤児["説明"]
              and "EADDRINUSE" not in (ただ落ち["説明"] or ""))
        out["孤児が口を掴んでいる"] = (bool(ok),
            "元気なうちに口 [8080] を覚え、落ちたときに空なら「落ちている」、"
            "別のプロセスが掴んでいれば「起こしても即死する」と言い分けた" if ok
            else "健全=%s（覚えた口=%s）／ただ落ち=%s／孤児=%s"
                 % ((健全 or {}).get("判定"), 覚えた,
                    (ただ落ち or {}).get("説明", "")[:30],
                    (孤児 or {}).get("説明", "")[:40]))

        # ── 心拍が嘘をついている（定時は死んでいるのに心拍だけ新しい） ──
        # **通るべき側を2つ置く。**手で走らせただけ（期限内）で鳴っては
        # 知らせが読まれなくなり、期限を過ぎても鳴らなければ素通りする。
        前 = 帳簿(PROBE_LABEL)
        with open(PROBE_PULSE, "w") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds")}))
        契 = dict(c.get(PROBE_LABEL))
        契["間隔"] = 60
        期限 = 60 * 遅れの許容 + 遅れの底上げ
        土 = {"runs": 前.get("runs"), "走り出した": 前.get("走り出した"),
             "心拍": time.time() - 3600}
        def _よむ(起, 契約=契):
            覚 = {"いつ": time.time() - 10,
                  "仕事": {PROBE_LABEL: dict(土, 起きていた=起)}}
            return _ひく(点呼(覚え=覚, 契約={PROBE_LABEL: 契約})[0], PROBE_LABEL)
        手で1回 = _よむ(0)                       # 期限内・心拍だけ新しい
        嘘 = _よむ(期限 + 60)                     # 期限切れ・心拍だけ新しい
        ok = bool(手で1回 and 手で1回["判定"] == 生 and 嘘 and 嘘["判定"] == 外)
        out["心拍が嘘をついている"] = (ok,
            "期限内の手動は鳴らさず、期限切れで心拍だけ新しい回を「%s」と読んだ"
            % 嘘["判定"] if ok
            else "期限内=%s / 期限切れ=%s（期限内は黙り、期限切れは鳴るのが正しい）"
                 % ((手で1回 or {}).get("判定"), (嘘 or {}).get("判定")))

        # ── 宣言: 既定は鳴り、1行書けば黙り、消し忘れは鳴る ──
        名 = "silence-probe"
        # 書き置き（`_` で始まる鍵）を宣言として数えないこと。
        # **`生` という名前を使わないこと。**モジュールの判定名（生きている）を
        # 関数の中で代入すると、その関数の中では最初から局所変数になり、
        # **前のほうで判定名として読んでいる行が全部 UnboundLocalError になる**。
        try:
            with open(宣言ファイル) as f:
                宣言の生 = json.load(f)
            書き置き = [k for k in 宣言の生 if k.startswith("_")]
        except (OSError, ValueError):
            書き置き = []
        書き置きを無視 = all(k not in 宣言() for k in 書き置き)
        素 = {"pulse:x": {"名前": 名, "元": "心拍だけ", "心拍名": 名, "宣言": None}}
        黙る = {"pulse:x": dict(素["pulse:x"], 宣言={"呼ばれて走る": "試験"})}
        忘れ = {"宣言:x": {"名前": "居ない仕事", "元": "宣言だけ", "心拍名": "居ない仕事"}}
        a = _ひく(点呼(覚え={"いつ": time.time(), "仕事": {}}, 契約=素)[0], "pulse:x")
        b_ = _ひく(点呼(覚え={"いつ": time.time(), "仕事": {}}, 契約=黙る)[0], "pulse:x")
        d = _ひく(点呼(覚え={"いつ": time.time(), "仕事": {}}, 契約=忘れ)[0], "宣言:x")
        ok = (a and a["判定"] == 契約なし and b_ and b_["判定"] == 生
              and d and d["判定"] == 契約なし)
        ok = bool(ok) and 書き置きを無視
        out["宣言"] = (ok,
            "決めていないものは鳴り、1行書けば黙り、消し忘れは鳴り、"
            "書き置き %d 件は数えない" % len(書き置き) if ok
            else "決めていない=%s 書いた=%s 消し忘れ=%s 書き置きを無視=%s"
                 % ((a or {}).get("判定"), (b_ or {}).get("判定"),
                    (d or {}).get("判定"), 書き置きを無視))

        # ── 黙り: 期限を過ぎても走らない ──
        # **起きていた時計を積む側は、下で別に試す。**ここは判定だけ。
        前 = 帳簿(PROBE_LABEL)
        契 = dict(c.get(PROBE_LABEL))
        契["間隔"] = 60
        # **心拍も止まっていること。**心拍だけ新しければ、それは上の「嘘」のほう。
        try:
            os.unlink(PROBE_PULSE)
        except OSError:
            pass
        # **走り出した時刻も持たせる。**本物の点呼は必ず持っているので、
        # ここで省くと「前の点呼より後に走った」に化ける（2026-09-23、Linux で踏んだ）。
        覚え = {"いつ": time.time() - 10, "仕事": {PROBE_LABEL: {
            "runs": 前.get("runs"), "走り出した": 前.get("走り出した"), "心拍": None,
            "起きていた": 60 * 遅れの許容 + 遅れの底上げ + 60}}}
        所見, _ = 点呼(覚え=覚え, 契約={PROBE_LABEL: 契})
        判 = _ひく(所見, PROBE_LABEL)
        ok = bool(判 and 判["判定"] == 黙)
        out["黙り"] = (ok, "期限を過ぎて走っていない仕事を「%s」と読んだ" % 判["判定"]
                       if ok else "「%s」と読んだ" % (判 or {}).get("判定"))

        # ── 起きていた時計: 近い点呼だけ積み、空いた点呼は積まない ──
        契 = dict(c.get(PROBE_LABEL))
        契["間隔"] = 60
        b = 帳簿(PROBE_LABEL)
        土台 = {"いつ": 1000.0, "仕事": {PROBE_LABEL: {
            "runs": b.get("runs"), "走り出した": b.get("走り出した"),
            "心拍": 心拍時刻("silence-probe"), "起きていた": 0}}}
        _, 近 = 点呼(いま=1010.0, 覚え=土台, 契約={PROBE_LABEL: 契})
        _, 遠 = 点呼(いま=1000.0 + 起きていたと数える上限 + 60,
                     覚え=土台, 契約={PROBE_LABEL: 契})
        積んだ = 近["仕事"][PROBE_LABEL]["起きていた"]
        積まなかった = 遠["仕事"][PROBE_LABEL]["起きていた"]
        ok = 積んだ == 10 and 積まなかった == 0
        out["寝ていた間は数えない"] = (ok,
            "10秒あとの点呼は10秒積み、%d秒あいた点呼は積まなかった"
            % (起きていたと数える上限 + 60) if ok
            else "近い点呼で %s 秒・空いた点呼で %s 秒 積んだ" % (積んだ, 積まなかった))

        # ── 台帳から消えるか ──
        # **心拍を置き直してから外す。**上の「黙り」で消したままだと、
        # 「仕事は消えたのに心拍だけ残った」を試せない。
        with open(PROBE_PULSE, "w") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds")}))
        import schedlib as _s
        _s.使い捨て削除(PROBE_LABEL, plist置き場=PROBE_PLIST)
        c2 = 契約たち()
        消えた = PROBE_LABEL not in c2
        # 心拍だけ残ると「契約が無い」に出るはず。**これが最後の網。**
        残り = c2.get("pulse:silence-probe")
        out["台帳"] = (載った and 消えた and bool(残り),
                       "登録で載り、外して消え、心拍だけ残った仕事は「%s」に出た"
                       % 契約なし if (載った and 消えた and 残り)
                       else "載った=%s 消えた=%s 心拍だけの検出=%s"
                            % (載った, 消えた, bool(残り)))
    except Exception as e:
        out.setdefault("例外", (False, "%s: %s" % (type(e).__name__, e)))
    finally:
        _probe_remove()
    return out


def _ひく(所見, 鍵):
    for s in 所見:
        if s["鍵"] == 鍵:
            return s
    return None


# ── 表に出す ──────────────────────────────────────────────

def width(t):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def pad(t, to):
    return t + " " * max(0, to - width(t))


def main():
    flags = {a for a in sys.argv[1:] if a.startswith("-")}

    if "--verify" in flags:
        res = verify()
        print("黙りの見え方（この機械で実際に走らせて確かめた）\n")
        for k, (ok, why) in res.items():
            print("  %s %s %s" % ("○" if ok else "★", pad(k, 22), why))
        return 0 if all(ok for ok, _ in res.values()) else 1

    所見, 新 = 点呼()
    if "--json" in flags:
        print(json.dumps(所見, ensure_ascii=False, indent=2))
    else:
        鳴 = [s for s in 所見 if s["判定"] in 鳴る判定]
        if "--quiet" not in flags:
            for s in 所見:
                mark = "●" if s["判定"] in 鳴る判定 else "·"
                print("  %s %s %s %s" % (mark, pad(s["名前"], 18),
                                         pad(s["判定"], 22), s["説明"]))
            print("\n  %d 本を点呼して、%d 本が鳴っている。" % (len(所見), len(鳴)))
        elif 鳴:
            for s in 鳴:
                print("  ● %s %s %s" % (pad(s["名前"], 18), pad(s["判定"], 22), s["説明"]))
    if "--no-save" not in flags:
        書く覚え(新)
    return 0


if __name__ == "__main__":
    sys.exit(main())
