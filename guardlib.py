"""guardlib — 見張りたちが共有する部品。

## なぜ共有に変えたか

もとは同じコードを4つの見張りに書き写していた。理由は
「共通の部品が壊れると、見張りが揃って黙る」だった。

その考えは間違っていた。実際に起きたのは逆で、

  - 2026-08-30、watchdog を編集したときに beat と pulse_age を巻き込んで消し、
    NameError で落ちた。書き写しを導入したその日のうちに事故になった。
  - 同じ日に数えたら env_value は10ファイル、notify は6ファイルに増えていた。
  - 4つの beat のうち line-guard だけ既に中身がずれていた。ずれていたのは
    「わざと共有していない」と主張している説明文そのものだった。

**独立は、同じ文字列を別々に持つことでは買えない。**
見張りの独立を支えているのは、4つが別のプロセス・別の時計・別の判断で
動いていることであって、コードが別の場所に書いてあることではない。

## 共有したもの / しなかったもの

共有したのは、判断を含まない道具だけ（ファイルの読み書き、通知、鍵）。
**「何を見るか」「いつ手を出すか」は各見張りが自分で持っている。**
そこを共有すると、1つの判断ミスが4つに同時に効くので、そちらは今も分けてある。

## 単一障害点であることは認める

このファイルが壊れれば4つとも起動しない。書き写しはその危険を避けていた。
代わりに置いたのが下の selftest で、install が入れるたびに走らせる。
**重複で守るのではなく、検査で守る**に切り替えた、という整理になる。

    python3 guardlib.py --selftest

## 2026-08-31 の事故を受けて足したもの

この日、見張り2人が23分間、互いを殺し合って止まった。
Mac が 19:54〜20:26 寝て、起きた瞬間に両方の心拍が同時に古くなり、

    watchdog   → model-guard を kickstart -k で蹴る（＝走っている最中なら殺す）
    model-guard→ watchdog    を kickstart -k で蹴る

どちらも起動直後に相手を蹴るので、**どちらも心拍を書く前に殺され続けた**。
心拍が新しくならないので、相手からは永久に「死んでいる」ように見える。
50回ずつ「蹴った（成功）」と記録しながら、一度も直っていなかった。
10秒ちょうどの周期は launchd の既定の再起動間隔と一致していた。
つまり **launchd の再起動制限だけが暴走の歯止めだった**。

そこで、この4つをここに置いた。どれか1つでも効けばあの事故は起きない。

  1. kickstart は**走っている相手を殺さない**（-k をやめた）
  2. kickstart は**同じ相手を短い間に何度も蹴らない**（蹴る予算）
  3. **寝起きは判断しない**（awake_seconds。寝ている間は誰も心拍を打てない）
  4. **知らせは消えたら溜める**（起き抜けはネットがまだ無い。100回の警報が
     全部 "Discord に送れなかった" で消えたのが、この日いちばん困ったこと）
"""

try:
    import fcntl                      # POSIX
    msvcrt = None
except ImportError:                   # Windows
    fcntl = None
    try:
        import msvcrt
    except ImportError:               # どちらも無い機械
        msvcrt = None
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

def 道具の呼び方(argv):
    """家の道具を呼ぶときの、この OS での並べ方。

    **Windows は拡張子の無いファイルを直に実行できない。**`#!/usr/bin/env python3` は
    POSIX の約束なので、Windows では `python <ファイル>` と並べ直す必要がある
    （2026-09-23、実機で `claw status` が WinError 193 で落ちた）。
    POSIX では何も変えない（shebang がそのまま効く）。"""
    if os.name != "nt" or not argv:
        return list(argv)
    先 = str(argv[0])
    if os.path.splitext(先)[1]:          # .py / .exe など拡張子があるものはそのまま
        return list(argv)
    try:
        with open(先, "rb") as f:
            頭 = f.readline(200)
    except OSError:
        return list(argv)
    if 頭.startswith(b"#!") and b"python" in 頭:
        return [sys.executable, 先] + list(argv[1:])
    if 頭.startswith(b"#!") and (b"sh" in 頭 or b"bash" in 頭):
        return ["bash", 先] + list(argv[1:])
    return list(argv)


def 鍵を試す(f):
    """開いているファイルに、重ならない鍵を試しに掛ける。取れたら True。

    **この家の鍵は全部「試し取り」**——取れなければ待たずに引き返す（二重に走らない）。
    プロセスが死ねば OS が必ず外すので、後片付けの実行に頼らない。
    POSIX は flock、Windows は msvcrt.locking（2026-09-23、Windows で
    `import fcntl` だけで claw と guard-drill が1行も動かなかったので足した）。"""
    if fcntl is None and msvcrt is None:
        # **鍵の仕組みが無い機械では、二重に走らないことを保証できない。**
        # ここで False を返すと見張りが永久に走らなくなるので True を返すが、
        # 「鍵が取れた」ではなく「鍵が無い」である。嘘をつかないよう、
        # 呼んだ側が知りたいときのために 鍵の仕組み() を用意してある。
        return True
    try:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except (OSError, BlockingIOError, ValueError):
        return False


def 鍵の仕組み():
    """この機械で鍵に使えるもの。無ければ None（＝二重走行は防げない）。"""
    return "flock" if fcntl is not None else ("msvcrt" if msvcrt is not None else None)


def 鍵を返す(f):
    """鍵を外す。閉じれば OS が外すので、**失敗しても黙って進んでよい。**"""
    if fcntl is None and msvcrt is None:
        return
    try:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_UN)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except (OSError, ValueError):
        pass


OPENCLAW = os.path.expanduser("~/.openclaw")
ENV_FILE = os.path.join(OPENCLAW, ".env")
PULSE_DIR = os.path.join(OPENCLAW, "pulse")
LOG_DIR = os.path.join(OPENCLAW, "logs")
PLIST_DIR = os.path.expanduser("~/Library/LaunchAgents")

# 届かなかった知らせの置き場。ここに溜めて、次に送れたときに一緒に出す。
PENDING_FILE = os.path.join(OPENCLAW, "pending-notify.jsonl")
PENDING_MAX = 40                # これ以上は溜めない（古いものから捨てる）
PENDING_TTL = 24 * 3600         # 一日たった知らせは、もう届けても意味がない

# 訓練が走っているあいだ置かれる印。guard-drill が作って、終わったら消す。
#
# **記録にもそれを書く。** 印は置いてあったが、置いただけで誰も読んでいなかった。
# guard-drill 自身の説明文には「見張りの記録を後から読む人が、本物の障害と
# 訓練を取り違えないため」と書いてあるのに、その取り違えを防ぐ側が
# 実装されていなかった。実際、8/31 の事故を追うときに 05:30 の
# 「30分止まっている」が訓練なのか本物なのかを、時刻から推測する羽目になった。
DRILL_MARK = os.path.join(OPENCLAW, "drill-in-progress")

# 誰をいつ蹴ったかの控え。見張り同士で共有する（別プロセスなので、ここでしか分からない）。
KICK_FILE = os.path.join(OPENCLAW, "kick-history.json")
# 同じ相手を、これより短い間に何度も蹴らない。
# 本当に死んでいるなら1回で起きる。何度も蹴らないと起きない相手は、
# 蹴っても直っていないので、回数を増やしても意味がない。
KICK_MIN_GAP = 300
# 走り続けている相手を「固まっている」と見なすまでの秒数。
# ここを超えたときだけ、殺してから起こす。
KICK_HUNG_AFTER = 900

# 記録がこれを超えたら古いほうを捨てる。
# /tmp の cloudflared のログが30MBまで育っていたので、こちらは先に手を打っておく。
# 鍵に塞がれっぱなしのまま、これより長く何もできていなければ知らせる。
# ふつうの巡回は数秒で終わるので、15分塞がれているなら相手は固まっている。
BLOCKED_MAX = 900

# ── 外へ出る量の予算 ──────────────────────────────────────
#
# **外に出た知らせは取り消せない。**プロセスを巻き戻しても、届いた通知は消えない。
# だから出る前に数えて、出過ぎたら止める。
#
# 2026-09-13、点呼の誤報（走っている最中を「走り切れていない」と読んだ）で
# **1日に262回**知らせを出した。平常時のログに出る通知は1日4〜12件なので、
# 20倍以上。知らせが多すぎると読まれなくなるので、**黙るのと同じ害**になる。
#
# **正直に**: 上の 4〜12件は「送れなかった／溜めた」ログ行の数で、
# 成功した送信はログに残らないため、平常時の実数は後から測れない。
# この予算の記録が、その最初の実測になる。
#
# 1時間15通は、平常時の1日ぶんより多い。**本物の事故は素通りし、
# 暴走（実測で1時間63件）だけが当たる**幅にしてある。
送信の窓 = 3600
送信の予算 = 15
BUDGET_FILE = os.path.join(OPENCLAW, "notify-budget.json")
# **予算のうち、初めて出た知らせのために取り置くぶん。**
# 財布は家じゅうで1つなので、同じ文面で鳴き続ける見張りが1本いるだけで、
# **本物の警報が黙って捨てられる**（2026-09-23、5:30 の訓練の赤が実際にそうなった）。
# 繰り返しは先に止め、初めて出た顔のぶんだけ最後まで残しておく。
取り置き = 5
# 捨てた知らせの中身。**捨てたことだけでなく、何を捨てたかを残す。**
# 溜めて後から全部送ると騒音になるので、送らずにここへ積み、
# 窓が変わったときに先頭行だけをまとめて伝える。
DROPPED_FILE = os.path.join(OPENCLAW, "捨てた知らせ.jsonl")
DROPPED_MAX = 200

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_KEEP_BYTES = 512 * 1024

# ── 「いま触っているから手を出さないで」の合図 ──────────────
#
# 人や道具が**わざと** gateway を止めている最中に、見張りが起こしにくると
# 取り合いになる。2026-09-06、更新の失敗を直している最中に watchdog が
# 14回数えて gateway を再登録し、書き戻したばかりの設定を消した。
# 直す側と見張る側が、互いを障害と見なして殴り合う形。
#
# **必ず期限を付ける。** 期限の無い「見ないで」は、置き忘れたときに
# 見張りを永久に黙らせる。この家で一番怖いのは止まることではなく黙ることなので、
# 印そのものが黙らせる装置になってはいけない。置いた側が消し忘れても、
# 期限が来れば見張りは自分で見張りに戻る。
MAINT_MARK = os.path.join(OPENCLAW, "maintenance")
MAINT_LOCK = os.path.join(OPENCLAW, "maintenance.lock")
MAINT_MAX = 3600            # どんなに長くてもここで切れる
MAINT_DEFAULT = 900         # 何も言われなければ15分

_maint_lock_fd = None       # 置き主が握り続ける。死ねば OS が離す。


def maintenance_hold(why, seconds=MAINT_DEFAULT, by="unknown", tie_to_process=False):
    """手入れ中の印を置く。置けたら True。

    seconds は MAINT_MAX で頭打ちにする。呼ぶ側が「念のため長めに」と
    書けてしまうと、それは事実上の永久停止になるため。

    ## tie_to_process

    True にすると、**印がこのプロセスの命と結びつく**。プロセスが消えれば
    印もその場で無効になり、期限を待たずに見張りが戻る。

    2026-09-07、`openclaw-update` が途中で殺されて `finally` の後片付けが
    走らず、印だけが残った。gateway が落ちたまま**30分ぶん誰も直しに行かない**
    状態になった。見張りを増やしたぶん、置き主が死んだときの被害も増えている。

    **PID を書いて生死を見る方法は採らない。**番号は使い回されるので、
    無関係のプロセスが同じ番号を取った瞬間に「生きている」と誤読する。
    flock は**プロセスが死ねば OS が必ず離す**——SIGKILL でも、
    ウィンドウごと閉じられても離れる。後片付けの実行に頼らずに済む。

    人が手で置く印（`claw hold`）はこれを使わない。あちらは打った瞬間に
    プロセスが終わるので、結びつけると**置いた次の瞬間に無効になる**。
    人が置いた印は、期限だけが頼りでよい。
    """
    global _maint_lock_fd
    seconds = max(60, min(int(seconds), MAINT_MAX))
    until = datetime.now().timestamp() + seconds
    mark = {"until": until, "why": why, "by": by}
    if tie_to_process:
        try:
            f = open(MAINT_LOCK, "w")
            if not 鍵を試す(f):
                raise BlockingIOError
            _maint_lock_fd = f      # プロセスが終わるまで握っておく
            mark["tied"] = True
            mark["pid"] = os.getpid()
        except (OSError, BlockingIOError):
            pass                    # 取れなければ期限だけが頼り。印自体は置く。
    return atomic_write(MAINT_MARK, json.dumps(mark, ensure_ascii=False))


def _holder_gone():
    """命と結びつけた印の、置き主がもう居ないか。

    鍵を**試しに取ってみる**。取れたら誰も握っていない＝置き主は死んでいる。
    取れたぶんはすぐ返す（こちらが新しい置き主になってはいけない）。

    **分からないときは「居る」と読む。**この家の他の判定は「迷ったら見張る
    ほうへ倒す」だが、ここだけは逆にする。誤って「居ない」と読むと、
    本物の手入れの最中に見張りが殴りに来る——2026-08-31 と同じ形で、
    これを止める後ろ盾は無い。誤って「居る」と読んだ場合は、期限が最長1時間で
    必ず切る。**後ろ盾がある側に倒す。**"""
    try:
        f = open(MAINT_LOCK, "a")
    except OSError:
        return False
    try:
        if not 鍵を試す(f):
            raise BlockingIOError
    except (OSError, BlockingIOError):
        return False                # 取れない＝誰かが握っている＝生きている
    else:
        return True                 # 取れた＝置き主は居ない
    finally:
        f.close()                   # 試した鍵はすぐ返す


def maintenance_clear():
    """印を外す。無ければ何もしない。"""
    try:
        os.unlink(MAINT_MARK)
    except OSError:
        pass


def maintenance():
    """いま手入れ中か。(そうか, 説明) を返す。

    期限切れの印はここで捨てる。読む側が捨てるので、置いた側が
    途中で落ちても、次に誰かが見た時点で元に戻る。
    印が壊れていたら「手入れ中ではない」と読む。**迷ったら見張るほうへ倒す。**"""
    try:
        with open(MAINT_MARK) as f:
            m = json.load(f)
        until = float(m["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return False, ""
    left = until - datetime.now().timestamp()
    if left <= 0:
        maintenance_clear()
        return False, ""
    # 置き主の命と結びついた印は、置き主が消えた時点で無効。期限は待たない。
    if m.get("tied") and _holder_gone():
        maintenance_clear()
        return False, ""
    return True, f"{m.get('by', '誰か')} が手入れ中（残り {int(left) // 60 + 1} 分・{m.get('why', '')}）"


def stand_down(guard, dry=False):
    """手入れ中なら「何もせずに帰れ」と答える。(そうか, 説明) を返す。

    呼ぶ側は True を受けたら、その場で return すること。**心拍は
    Guard.run が finally で必ず残す**ので、ここで足す必要はない。
    黙って休むと、ほかの見張りが心拍の途絶を「死んだ」と読んで蹴りにくる。

    `--dry-run` は何も触らないので、印があっても止めない。
    調べているだけの人の邪魔をしないため。

    ## なぜ要るか

    印を置く仕組みは前からあったのに、2026-09-06 の時点で見ていたのは
    watchdog だけだった。line-guard は openclaw の更新中に gateway を
    3回起こし直し、そのたびに「LINEから届かない」と誤診して
    トンネルを6回張り替え、URL を6回変えた。
    **印は、置く側ではなく読む側が揃っていないと意味がない。**
    """
    if dry:
        return False, ""
    held, why = maintenance()
    if not held:
        return False, ""
    guard.log(f"手入れ中なので何もしない（{why}）")
    return True, why


def honors_mark(path):
    """そのファイルが手入れ中の印を読んでいるか。読んでいなければ False。

    一覧を手で持たない。持つと、書き換えたのに一覧を直し忘れた日から
    嘘をつきはじめる（この一式が何度もやられている形）。**実物を見る。**"""
    try:
        with open(path, errors="ignore") as f:
            src = f.read()
    except OSError:
        return False
    return "stand_down(" in src or "maintenance()" in src


def atomic_write(path, text):
    """書き換えの途中で電源が落ちても、壊れた中身が残らないようにする。

    心拍と覚え書きは**別のプロセスが同時に読む**。
    open(w) は先に中身を空にしてから書くので、その一瞬に読まれると
    JSON として壊れたものが読める。読んだ側は例外を握りつぶして
    「一度も走っていない」と解釈するので、**死んでいないものを死んだ**と数える。
    書き上げてから名前を差し替えれば、読む側には古いか新しいかしか見えない。"""
    tmp = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def awake_seconds():
    """このMacが起きてから何秒たったか。分からなければ None。

    **寝ている間は、どの見張りも心拍を打てない。**
    起きた直後に「30分止まっている」と読めるのは当たり前で、
    それは相手が死んだ証拠ではない。ここを見ないと、
    蓋を閉めて開けるたびに全員が「みんな死んだ」と判断する。

    2026-08-31 の事故はこれが引き金だった（19:54 就寝 → 20:26 起床 →
    起きた瞬間に両方の心拍が同時に32分ぶん古くなった）。"""
    # macOS: 起きた時刻そのものが読める
    try:
        out = subprocess.run(["sysctl", "-n", "kern.waketime"],
                             capture_output=True, text=True, timeout=5).stdout
        # "{ sec = 1788175607, usec = 773235 } Mon Aug 31 20:26:47 2026"
        sec = int(out.split("sec = ", 1)[1].split(",", 1)[0])
        return max(0.0, time.time() - sec)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    # Linux: 眠っていた時間を含まない時計（CLOCK_MONOTONIC）と、含む時計
    # （CLOCK_BOOTTIME）の差が「眠っていた合計」。起きてからの秒数は、
    # **最後の目覚め以降**なので厳密には取れないが、
    # 「眠っていた合計が増えた＝さっき眠っていた」までは分かる。
    # ここでは**眠りを含まない時計**を返す。寝起きの誤報を消すにはそれで足りる
    # （寝ている間は誰も心拍を打てず、monotonic も進まないため）。
    try:
        if hasattr(time, "CLOCK_MONOTONIC"):
            return max(0.0, time.clock_gettime(time.CLOCK_MONOTONIC))
    except (OSError, AttributeError, ValueError):
        pass
    # Windows: 起動からの経過（眠っていた時間は含まない）
    try:
        import ctypes
        return max(0.0, ctypes.windll.kernel32.GetTickCount64() / 1000.0)
    except (AttributeError, OSError, ValueError):
        return None


# 起きてから、これだけ経つまでは心拍の古さで判断しない。
#
# **ここに「止まっていると決めるまでの秒数」を渡してはいけない。**
# 最初そう書いていたが、それだと qwc-guard（30時間）と訓練（3日）は
# **起床後それだけの間ずっと判断されない**ことになる。
# つまり寝るたびに、その2つの点検が丸ごと止まる。直したつもりで穴を開けていた。
#
# 見たいのは「launchd が定期実行を出し直す暇があったか」だけなので、
# 必要なのは短い一定の猶予でよい。いちばん長い定期実行が60秒おき、
# 日次のものも起床時にまとめて出し直されるので、5分あれば全員1回は走っている。
SETTLE_AFTER_WAKE = 300


def settling(margin=SETTLE_AFTER_WAKE):
    """いま「寝起きで、まだ判断してはいけない」時間帯か。

    **寝ている間は誰も心拍を打てない。** 起きた直後に「30分止まっている」と
    読めるのは当たり前で、相手が死んだ証拠ではない。
    分からないとき（sysctl が読めない等）は False にする。
    **見張りを止める側に倒さない**——判断できないなら、いつも通り判断する。"""
    awake = awake_seconds()
    return awake is not None and awake < margin


def env_value(key):
    """環境変数、無ければ ~/.openclaw/.env から拾う。

    鍵や自分を指すIDをコードに直書きしないための入り口。
    launchd から走るときは環境変数が渡らないので、ファイルからも読む。"""
    v = os.environ.get(key)
    if v:
        return v.strip()
    try:
        for row in open(ENV_FILE):
            row = row.strip()
            if row.startswith(f"{key}="):
                return row.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def pulse_age(name):
    """その見張りが最後に走り切ってから何秒たったか。一度も走っていなければ None。"""
    try:
        with open(os.path.join(PULSE_DIR, f"{name}.json")) as f:
            at = datetime.fromisoformat(json.load(f)["at"])
        return (datetime.now() - at).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ── 蹴り直す ──────────────────────────────────────────────

def _kick_history():
    try:
        with open(KICK_FILE) as f:
            h = json.load(f)
        return h if isinstance(h, dict) else {}
    except (OSError, ValueError):
        return {}


def _job_state(label):
    """(走っているか, 何秒走っているか)。分からなければ (None, None)。

    仕組み（launchd / systemd / 無し）は schedlib が知っている。ここは
    「走っているか」と「どれだけ走り続けているか」だけを見る。"""
    import schedlib
    b = schedlib.帳簿(label)
    if b is None:
        return None, None
    running = b.get("state") == "running" or bool(b.get("pid"))
    pid = b.get("pid")
    if not running or not pid:
        return bool(running), None
    e = subprocess.run(["ps", "-p", str(pid), "-o", "etimes="],
                       capture_output=True, text=True)
    try:
        return True, int(e.stdout.strip())
    except ValueError:
        return True, None


def _do_kick(label, kill):
    """実際に頼む。**OS への頼み方は schedlib が持つ**（launchd / systemd / 無い機械）。
    返すのは (どうしたか, 説明)。"""
    import schedlib
    return schedlib.蹴る(label, 殺す=kill,
                        path=os.path.join(PLIST_DIR, f"{label}.plist"))


def _budget_ok(label, min_gap):
    """同じ相手を短い間に何度も蹴らないための予算。取れたら True。

    本当に死んでいるなら1回で起きる。何度も蹴らないと起きない相手は、
    蹴っても直っていないので、回数を増やしても意味がない。
    2026-08-31 の蹴り合いは10秒おきに50回だった。1回目で直らなかったのだから、
    50回目も直らない。**効かない手を繰り返すのは、直しているのではなく壊している。**"""
    hist = _kick_history()
    last = hist.get(label)
    if last and min_gap:
        try:
            waited = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            if waited < min_gap:
                return False, int(waited)
        except ValueError:
            pass
    hist[label] = datetime.now().isoformat(timespec="seconds")
    atomic_write(KICK_FILE, json.dumps(hist, ensure_ascii=False))
    return True, None


def kickstart(label, min_gap=KICK_MIN_GAP, hung_after=KICK_HUNG_AFTER):
    """**時々走る仕事**（見張り・定時の仕事）を起こす。

    ここは一度、直っていないのに「入れ直した」と記録していた。
    launchctl kickstart は plist が外れていると
    `Could not find service ... in domain for user gui` で失敗するだけで、
    戻り値を捨てていたため、ログにだけ復旧したと書き残っていた。
    **嘘をつく見張りは、居ないより悪い。**

    **走っている相手は蹴らない。** 以前は `-k`（走っていれば殺してから起こす）を
    付けていた。見張り2人が互いを蹴る形になっていたので、
    **どちらも心拍を書く前に殺され続けた**。相手からは永久に死んで見える。
    走っているなら放っておけば自分で心拍を書く。それを待つのが正しい。
    ただし異常に長く（hung_after 秒）走り続けているものだけは、固まっているので殺す。

    **常駐しているもの（gateway・トンネル・受け口・ollama）にこれを使わないこと。**
    あれは「走っているのに黙っている」のを直すのが仕事なので、走っていることを
    理由に見送ると、いちばん直したい場面で何もしなくなる。そちらは restart_service。

    返すのは (どうしたか, 説明)。どうしたかは
      "kicked"   … 蹴った（起きたはず）
      "running"  … 走っている最中だったので手を出していない
      "waiting"  … さっき蹴ったばかりなので見送った
      "failed"   … 蹴れなかった
    **「蹴った」以外を「成功」と書かないこと。**"""
    running, for_secs = _job_state(label)
    hung = bool(hung_after and for_secs and for_secs >= hung_after)
    if running and not hung:
        return "running", f"走っている最中（{for_secs if for_secs is not None else '?'}秒）"

    ok, waited = _budget_ok(label, min_gap)
    if not ok:
        return "waiting", f"{waited}秒前に蹴ったばかり"

    how, why = _do_kick(label, kill=hung)
    if how == "kicked" and hung:
        why = f"{for_secs}秒走り続けていたので殺してから起こした"
    return how, why


def restart_service(label, min_gap=60):
    """**常駐しているもの**（gateway・トンネル・受け口・ollama）を入れ直す。

    こちらは走っていても殺して入れ直す。**それがこの関数の仕事**で、
    直したいのは「落ちている」ではなく「立っているのに答えない」ほうだから。

    min_gap があるのは、呼ぶ側の数え間違いで毎分入れ直しになるのを防ぐため。
    実際 model-guard には、5回諦めたあと**毎分 ollama を入れ直し続ける**
    経路が残っていた（fails が 5 を超えると通知の枝を外れて入れ直しの枝に落ちる）。
    呼ぶ側を直したうえで、ここにも底を敷いておく。"""
    ok, waited = _budget_ok(label, min_gap)
    if not ok:
        return "waiting", f"{waited}秒前に入れ直したばかり"
    return _do_kick(label, kill=True)


class Guard:
    """1つの見張りが持つ、記録・通知・心拍・鍵。

    置き場所は名前から決まる（~/.openclaw/logs/<名前>.log など）。
    見張りを1つ足すたびにパスを4本書くのをやめるため。"""

    def __init__(self, name):
        self.name = name
        self.log_path = os.path.join(LOG_DIR, f"{name}.log")
        self.state_path = os.path.join(OPENCLAW, f"{name}-state.json")
        self.lock_path = os.path.join(OPENCLAW, f"{name}.lock")
        self._lock = None

    # ── 記録 ──────────────────────────────
    def log(self, msg):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            self._rotate()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 訓練が走っている最中の行には、そう書いておく。
            # あとから読む人が、わざと壊したぶんと本物の障害を見分けられるように。
            drill = " [訓練]" if os.path.exists(DRILL_MARK) else ""
            with open(self.log_path, "a") as f:
                f.write(f"[{stamp}]{drill} {msg}\n")
        except OSError:
            pass

    def _rotate(self):
        """記録が育ちすぎたら、新しいほうだけ残す。

        line-guard.log には同じ行が767回並んでいた。放っておくと、
        いざ読みたいときに読めない大きさになる（/tmp の cloudflared は30MBだった）。
        別ファイルに退避せず切り詰めるのは、**古い記録より、
        いま読めることのほうが大事**だから。"""
        try:
            if os.path.getsize(self.log_path) <= LOG_MAX_BYTES:
                return
            with open(self.log_path, "rb") as f:
                f.seek(-LOG_KEEP_BYTES, os.SEEK_END)
                f.readline()          # 途中から読んだ最初の1行は捨てる
                tail = f.read()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            head = f"[{stamp}] ここより前の記録は大きくなりすぎたので捨てた\n".encode()
            atomic_write_bytes(self.log_path, head + tail)
        except OSError:
            pass

    # ── 通知 ──────────────────────────────
    def _捨てた(self, text, なぜ):
        """捨てた知らせを積む。**捨てた事実と中身の両方を残す。**"""
        try:
            行 = {"at": datetime.now().isoformat(timespec="seconds"),
                 "見張り": self.name, "なぜ": なぜ,
                 "先頭行": text.splitlines()[0][:200], "全文": text[:2000]}
            残 = []
            if os.path.exists(DROPPED_FILE):
                with open(DROPPED_FILE, errors="ignore") as f:
                    残 = f.read().splitlines()[-(DROPPED_MAX - 1):]
            残.append(json.dumps(行, ensure_ascii=False))
            atomic_write(DROPPED_FILE, "\n".join(残) + "\n")
        except (OSError, ValueError):
            pass

    def 捨てた知らせ(self, 以降=None):
        """積んである「捨てた知らせ」。(時刻, 見張り, 先頭行) の一覧。"""
        出 = []
        try:
            with open(DROPPED_FILE, errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if 以降 and d.get("at", "") < 以降:
                        continue
                    出.append((d.get("at"), d.get("見張り"), d.get("先頭行")))
        except OSError:
            pass
        return 出

    def notify(self, text, even_in_drill=False):
        """Discord に一言送る。

        宛先が分からないときは**黙って捨てず**ログに残す。
        見張りの知らせが届かないうえ、届いていないことすら分からないのが一番困る。
        gateway を通さず discord.com を直接叩くのは、
        gateway が死んでいるときにこそ知らせたいから。

        **送れなかったら溜めて、次に送れたときに一緒に出す。**
        2026-08-31、見張りが2人とも死んだという一番知らせるべき知らせが、
        約100回ぶん全部 "Discord に送れなかった" で消えた。
        起き抜けでネットがまだ立ち上がっていなかっただけで、
        30秒待てば送れた。**見張りが吠える場面は、通知が届かない場面と重なる。**
        だから送れないことを前提に作る。"""
        text = (text or "").strip() or "（中身のない知らせ）"

        # **訓練中は送らない。記録には残す。**
        #
        # 訓練は本物の見張りに偽の故障を見せるので、見張りは正直に警報を出す。
        # その結果、毎朝の訓練のたびに「qwc がうまく動いていません」と
        # 「qwc が直りました」の2通が本物の Discord に飛んでいた。
        # 嘘の警報が毎日届くと、**本物の警報を読まなくなる**。
        # 見張りが黙るのと同じくらい、狼少年になるのも困る壊れ方なので、
        # ここで止める。届く経路が生きているかは、訓練の notify が別に見る
        # （こちらは1通も送らずに、宛先が引けることだけ確かめる）。
        # **even_in_drill は、見張りの警報ではない知らせのための逃げ道。**
        # 上の理由は「訓練が出させた嘘の警報」を止めるためのもので、
        # claw が本人に送る用件には当てはまらない。訓練中に黙って
        # 捨てると、本人は送ったつもりのまま届かない。
        if os.path.exists(DRILL_MARK) and not even_in_drill:
            # 印は log() が自分で付けるので、ここでは書かない
            self.log("送るはずだった知らせ: " + text.splitlines()[0])
            return True

        tok = env_value("DISCORD_BOT_TOKEN")
        channel = env_value("DISCORD_CHANNEL_ID")
        if not tok or not channel:
            self.log("通知先が設定されていない（DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID）: " + text)
            print(text)
            return False

        # **予算を見る。出過ぎたら止めるが、黙って捨てない。**
        b = self._予算()
        前に抑えた = b.pop("前の窓で抑えた", 0)
        前の顔 = b.pop("前の窓の顔", [])
        if 前に抑えた:
            # 窓が変わった。**抑えたぶんがあったことは必ず伝える**——
            # 抑えたこと自体が黙りになると、予算が「黙らせる装置」になる。
            # **中身も出す。**件数だけだと、落ちたのが本物かどうか分からない。
            先頭 = [f"・{見}: {行}" for _t, 見, 行 in self.捨てた知らせ()[-5:]]
            self._post(tok, channel,
                       f"前の1時間で知らせを {前に抑えた} 件抑えました"
                       f"（1時間 {送信の予算} 通の上限）。"
                       + ("\n捨てたものの先頭行:\n" + "\n".join(先頭) if 先頭 else "")
                       + f"\n全文は {DROPPED_FILE} と各見張りの記録にあります。")
        # **同じ顔で鳴き続ける相手に、財布を全部使わせない。**
        顔 = (text.splitlines()[0][:80]).strip()
        見た = b.setdefault("顔", [])
        初めて = 顔 not in 見た
        if not 初めて and b["送った"] >= 送信の予算 - 取り置き:
            b["抑えた"] += 1
            self._予算を書く(b)
            self._捨てた(text, f"繰り返しの知らせ（残り {取り置き} 通は初めて出た知らせのための取り置き）")
            self.log("取り置きに手を付けないため送らなかった（同じ文面の繰り返し）: "
                     + 顔[:100])
            return False
        if b["送った"] >= 送信の予算:
            b["抑えた"] += 1
            self._捨てた(text, "予算を超えた")
            if not b.get("知らせた"):
                b["知らせた"] = True
                self._post(tok, channel,
                           f"知らせが1時間で {送信の予算} 通を超えました。"
                           f"ここから先はこの1時間、**送らずに記録だけ**にします。"
                           f"\n見張りが暴走している疑いがあります: guard-drill / silence.py")
            self._予算を書く(b)
            # **溜めない。**溜めると窓が変わった瞬間に全部届いて、
            # 抑えた意味が消える（騒音になる）。記録と「捨てた知らせ」に残す。
            self.log("予算を超えたので送らなかった: " + text.splitlines()[0][:120])
            return False

        sent_backlog = self._flush_pending(tok, channel)
        if self._post(tok, channel, text):
            b["送った"] += 1
            if 初めて:
                見た.append(顔)
                del 見た[:-60]
            self._予算を書く(b)
            if sent_backlog:
                self.log(f"溜まっていた知らせ {sent_backlog} 件も送った")
            return True
        self._hold(text)
        return False

    # ── 外へ出る量 ────────────────────────
    def _予算(self, いま=None):
        """(送ってよいか, これまでの本数, 抑えた本数, 窓の始まり)。

        **家じゅうで1つの財布。**見張りごとに持つと、5本が同時に暴走したときに
        5倍出る。ここは「外に出た総量」を見る場所なので、まとめて数える。"""
        いま = いま or time.time()
        try:
            with open(BUDGET_FILE) as f:
                b = json.load(f)
        except (OSError, ValueError):
            b = {}
        始まり = b.get("窓", 0)
        if いま - 始まり >= 送信の窓:
            b = {"窓": いま, "送った": 0, "抑えた": 0, "知らせた": False, "顔": [],
                 "前の窓で抑えた": b.get("抑えた", 0),
                 "前の窓の顔": b.get("顔", [])}
        return b

    def _予算を書く(self, b):
        try:
            atomic_write(BUDGET_FILE, json.dumps(b, ensure_ascii=False))
        except OSError:
            pass

    def _post(self, tok, channel, text):
        body = json.dumps({"content": text[:1950]}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel}/messages",
            data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bot {tok}",
                     "User-Agent": f"{self.name} (local, 1.0)"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
            return True
        except Exception:
            return False

    def _hold(self, text):
        """送れなかったぶんを溜める。

        **同じ文面は1件にまとめる。** 上の事故では10秒おきに同じ文が出続けた。
        そのまま溜めると、繋がった瞬間に100通が届くことになる。
        それは知らせではなく騒音で、本当に見たい1件が埋まる。"""
        rows = self._pending()
        now = datetime.now().isoformat(timespec="seconds")
        for r in rows:
            if r.get("text") == text:
                r["count"] = int(r.get("count", 1)) + 1
                r["last"] = now
                break
        else:
            rows.append({"at": now, "last": now, "count": 1, "text": text})
        if len(rows) > PENDING_MAX:
            rows = rows[-PENDING_MAX:]
        atomic_write(PENDING_FILE,
                     "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        self.log("Discord に送れなかったので溜めた: " + text.splitlines()[0])

    def _pending(self):
        rows = []
        try:
            with open(PENDING_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(r, dict) or not r.get("text"):
                        continue
                    try:
                        age = (datetime.now() - datetime.fromisoformat(r["at"])).total_seconds()
                        if age > PENDING_TTL:
                            continue      # 一日前の話をいま届けても仕方がない
                    except (ValueError, KeyError, TypeError):
                        pass
                    rows.append(r)
        except OSError:
            pass
        return rows

    def _flush_pending(self, tok, channel):
        rows = self._pending()
        if not rows:
            return 0
        sent = 0
        left = []
        for i, r in enumerate(rows):
            if left:                      # 一度失敗したら、残りは次回に回す
                left.append(r)
                continue
            n = int(r.get("count", 1))
            head = f"（届かなかった知らせ・{r.get('at', '')}"
            head += f"・同じものが{n}回）\n" if n > 1 else "）\n"
            if self._post(tok, channel, head + r["text"]):
                sent += 1
            else:
                left.append(r)
        if left:
            atomic_write(PENDING_FILE,
                         "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in left))
        else:
            try:
                os.unlink(PENDING_FILE)
            except OSError:
                pass
        return sent

    def tell_once(self, state, key, text):
        """同じ話を何度も言わない知らせ。**覚え書きを先に保存してから送る。**

        以前は `state[key] = True` を立てるだけで、保存は点検の最後だった。
        2026-08-31、見張りが最後まで走り切れずに殺され続けたとき、
        **保存に一度も到達しなかったので抑制が効かず**、同じ知らせを100回送ろうとした。
        知らせる前に保存すれば、たとえ直後に殺されても二度は言わない。

        state を書き換えるので、呼んだ側は同じ state を使い続けてよい。"""
        if state.get(key):
            return False
        state[key] = True
        self.save_state(state)
        self.notify(text)
        return True

    # ── 心拍 ──────────────────────────────
    def beat(self):
        """「今回ちゃんと走り切った」という跡を残す。ほかの見張りがこれを見る。

        失敗した回にも残す。相手が答えないことと、見張りが死んだことは別で、
        取り違えると直す相手を間違える。"""
        try:
            os.makedirs(PULSE_DIR, exist_ok=True)
            atomic_write(os.path.join(PULSE_DIR, f"{self.name}.json"),
                         json.dumps({"at": datetime.now().isoformat(timespec="seconds")}))
        except OSError:
            pass

    # ── 覚え書き ──────────────────────────
    def load_state(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self, state):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            atomic_write(self.state_path, json.dumps(state, ensure_ascii=False))
        except OSError:
            pass

    # ── 鍵 ────────────────────────────────
    def hold_lock(self):
        """同時に2つ走らないようにする。取れなければ False。

        手で走らせたぶんと launchd の定期実行が重なり、両方が「連続3回」と
        数えて gateway を2回入れ直したことがある。見張りが2つ同時に手を出すと、
        直すつもりで壊すことになる。

        **同じプロセスが二度取ってもよい。**いまは run() が先に取るので、
        自分で取っていた見張り（model-guard / watchdog）は2回目を呼ぶことになる。
        flock は同じプロセスでも fd が違えばぶつかるので、素朴に書くと
        **自分自身と取り合って False を返し、その見張りが永久に何もしなくなる。**"""
        if self._lock is not None:
            return True
        try:
            f = open(self.lock_path, "w")
            if not 鍵を試す(f):
                raise BlockingIOError
            self._lock = f          # プロセスが終わるまで握っておく
            return True
        except (OSError, BlockingIOError):
            return False

    # 見るだけの呼び方。鍵を取らない——`claw status` が
    # `line-guard --check` を毎回叩くので、ここを塞ぐと状態表示が嘘になる。
    #
    # **これは既定であって、決めつけではない。**どの呼び方が手を出すかは
    # 見張りごとに違う。判断を共有の層に置くと、1つの思い込みが全員に効く。
    # 実際 2026-09-08、`--report` を「手を出す側」と決めつけて訓練が落ちた
    # （訓練は `watchdog --report` の出力を見るので、鍵で塞ぐと何も出なくなる）。
    # 違う見張りは、自分で `G.LOOK_ONLY` を上書きすること。
    LOOK_ONLY = {"--check", "--report", "--dry-run", "--list", "--busy",
                 "--help", "-h"}

    # ── 落ちても心拍だけは残す ──────────────
    def run(self, main):
        """点検の本体を包んで、**何が起きても心拍だけは残す**。

        以前は watchdog が config-guard を timeout 付きで呼びながら
        TimeoutExpired を受けていなかった（141行・313行）。例外が上がると
        最後の save_state も beat も実行されないので、**生きているのに
        心拍を残さずに死ぬ**。相手はそれを「死んだ」と読んで蹴りにいく。
        2026-08-31 の蹴り合いは、この形からでも始められる。

        落ちたこと自体は握りつぶさない。記録に残し、知らせ、終了コードで返す。
        **心拍は「生きている」の印であって「正しく働いた」の印ではない**——
        正しく働いたかは訓練（guard-drill）が別に見ている。"""
        # **二重に走らせない。**見張りが2つ同時に手を出すと、直すつもりで壊す。
        # ここに置いたのは、1本ずつ足すと「どれに付いていてどれに付いていないか」の
        # 一覧を人が覚えることになり、その一覧は増やした日から嘘になるため。
        #
        # **塞がれっぱなしを見張る。**鍵を握ったまま固まった相手がいると、
        # 以降の巡回は毎回ここで帰る。それでも心拍は下の finally が残すので、
        # **何もしていないのに watchdog からは生きて見える**——この一式が
        # いちばん嫌う「壊れているのに壊れていると言わない」形になる
        # （2026-09-08、鍵を土台に移した日に実際にそうなることを確かめた）。
        #
        # 心拍は止めない。止めると、走っている最中の相手を蹴りにいって
        # 2026-08-31 の蹴り合いになる。**見張りは本当に生きている**ので、
        # 生死ではなく「働けていない時間」のほうを数える。
        if not (set(sys.argv[1:]) & self.LOOK_ONLY):
            state = self.load_state()
            if not self.hold_lock():
                since = state.get("blocked_since")
                if not since:
                    state["blocked_since"] = time.time()
                    self.save_state(state)
                elif time.time() - float(since) > BLOCKED_MAX:
                    mins = int((time.time() - float(since)) // 60)
                    self.tell_once(
                        state, "blocked_told",
                        f"見張り（{self.name}）が {mins} 分ずっと、"
                        f"もう1つ走っているという理由で何もしていません。\n"
                        f"**鍵を握ったまま固まったものが居ます。**\n"
                        f"心拍は出ているので、ほかの見張りからは生きて見えます。\n"
                        f"  ps aux | grep {self.name}\n"
                        f"  tail ~/.openclaw/logs/{self.name}.log")
                self.log("もう1つ走っているので、この回は何もしない")
                self.beat()
                return 0
            if state.pop("blocked_since", None) is not None:
                state.pop("blocked_told", None)
                self.save_state(state)

        code = 1
        try:
            code = main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 0
        except BaseException:
            import traceback
            tb = traceback.format_exc()
            self.log("点検の途中で落ちた:\n" + tb)
            if not getattr(self, "quiet_crash", False):
                sys.stderr.write(tb)
            state = self.load_state()
            self.tell_once(state, "crashed_told",
                           f"見張り（{self.name}）が点検の途中で落ちました。"
                           f"\n  {tb.strip().splitlines()[-1][:300]}"
                           f"\n心拍だけは残しているので、ほかの見張りは蹴りにきません。"
                           f"\n  tail ~/.openclaw/logs/{self.name}.log")
            code = 1
        else:
            state = self.load_state()
            if state.pop("crashed_told", None):
                self.save_state(state)
        finally:
            self.beat()
        return code


def atomic_write_bytes(path, data):
    tmp = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def trim_file(path, max_bytes=8 * 1024 * 1024, keep_bytes=1024 * 1024):
    """**他のプロセスが開いたまま書いているログ**を、その場で切り詰める。

    cloudflared のログが32MBまで育っていた。誰も回していないので、
    いざ障害を追いたいときに読めない大きさになる。

    **名前を差し替える方式（atomic_write）をここに使ってはいけない。**
    書いている側は古いほうのファイルを掴んだままなので、
    差し替えた瞬間に**以後の記録がどこにも残らなくなる**。
    見えるのは「ログが伸びなくなった」だけで、壊れたことに気づけない。
    ——これはこの一式が何度も踏んでいる「黙って壊れる」の形そのものなので、
    ここでは中身だけ入れ替える（logrotate の copytruncate と同じ考え方）。

    launchd の書き出し先は追記で開かれるので、切り詰めても次の行は末尾に付く。"""
    try:
        if os.path.getsize(path) <= max_bytes:
            return False
        with open(path, "r+b") as f:
            f.seek(-keep_bytes, os.SEEK_END)
            f.readline()              # 途中から読んだ最初の1行は捨てる
            tail = f.read()
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            head = f"--- [{stamp}] ここより前は大きくなりすぎたので捨てた ---\n".encode()
            f.seek(0)
            f.write(head + tail)
            f.truncate()
        return True
    except OSError:
        return False


def notify_target():
    """知らせの宛先が引けるか。**1通も送らずに確かめる。**

    2026-08-31、見張りが2人とも死んだという一番知らせるべき知らせが
    約100回ぶん全部消えた。原因は起き抜けでネットがまだ無かっただけで、
    鍵も宛先も正しかった。**届く経路が生きているかを、誰も毎日は見ていなかった。**

    確かめるのに1通送るのは筋が悪い（毎日届く「点検です」は、
    そのうち読まれなくなる）。宛先を GET するだけなら何も残らない。

    返すのは (通ったか, 説明)。"""
    tok = env_value("DISCORD_BOT_TOKEN")
    channel = env_value("DISCORD_CHANNEL_ID")
    if not tok:
        return False, "DISCORD_BOT_TOKEN が無い"
    if not channel:
        return False, "DISCORD_CHANNEL_ID が無い"
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel}",
        headers={"Authorization": f"Bot {tok}", "User-Agent": "guardlib (local, 1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            name = json.loads(r.read()).get("name") or "?"
        return True, f"宛先が引ける（#{name}）"
    except urllib.error.HTTPError as e:
        return False, f"宛先に届かない（HTTP {e.code}・鍵か宛先が違う）"
    except Exception as e:
        return False, f"宛先に届かない（{type(e).__name__}）"


def selftest():
    """このファイルが壊れていないかを、書き捨ての場所で確かめる。

    共有にした代わりに置いた検査。install が入れるたびに走らせる。"""
    import tempfile
    global OPENCLAW, PULSE_DIR, LOG_DIR, PENDING_FILE, KICK_FILE, BUDGET_FILE, DROPPED_FILE
    keep = (OPENCLAW, PULSE_DIR, LOG_DIR, PENDING_FILE, KICK_FILE,
            BUDGET_FILE, DROPPED_FILE)
    tmp = tempfile.mkdtemp(prefix="guardlib-test-")
    ok = []
    try:
        OPENCLAW = tmp
        PULSE_DIR = os.path.join(tmp, "pulse")
        LOG_DIR = os.path.join(tmp, "logs")
        PENDING_FILE = os.path.join(tmp, "pending-notify.jsonl")
        BUDGET_FILE = os.path.join(tmp, "notify-budget.json")
        DROPPED_FILE = os.path.join(tmp, "捨てた知らせ.jsonl")
        KICK_FILE = os.path.join(tmp, "kick-history.json")

        g = Guard("selftest")
        g.log_path = os.path.join(LOG_DIR, "selftest.log")
        g.state_path = os.path.join(tmp, "selftest-state.json")
        g.lock_path = os.path.join(tmp, "selftest.lock")

        g.beat()
        age = pulse_age("selftest")
        ok.append(("心拍を書いて読める", age is not None and age < 5))

        g.save_state({"a": 1})
        ok.append(("覚え書きが往復する", g.load_state().get("a") == 1))

        g.log("テスト")
        ok.append(("記録が書ける", os.path.exists(g.log_path)))

        # 訓練中の行には、そう書いてあること
        global DRILL_MARK
        keep_mark = DRILL_MARK
        DRILL_MARK = os.path.join(tmp, "drill-in-progress")
        g.log("印が無いとき")
        open(DRILL_MARK, "w").close()
        g.log("印があるとき")
        body = open(g.log_path).read()
        DRILL_MARK = keep_mark
        ok.append(("訓練中の行はそう分かる",
                   "[訓練] 印があるとき" in body and "[訓練] 印が無いとき" not in body))

        ok.append(("鍵が取れる", g.hold_lock() is True))

        ok.append(("無い心拍は None", pulse_age("いない見張り") is None))
        ok.append(("無い鍵は None を返す", env_value("ZZ_NOT_A_REAL_KEY") is None))

        # ── 書き換えの途中で壊れた中身が見えない ──
        p = os.path.join(tmp, "atomic.json")
        atomic_write(p, '{"x":1}')
        ok.append(("書き上げてから差し替える", json.load(open(p))["x"] == 1))
        ok.append(("書き損じが残らない",
                   not [n for n in os.listdir(tmp) if ".tmp" in n]))

        # ── 寝起きが分かる ──
        aw = awake_seconds()
        ok.append(("起きてからの秒数が読める", aw is not None and aw >= 0))
        ok.append(("十分に起きていれば寝起き扱いにしない", settling(1) is False))
        ok.append(("起きた直後は寝起き扱いになる",
                   settling((aw or 0) + 10_000) is True))
        # 猶予は短い一定値であること。しきい値をそのまま渡す作りだと、
        # qwc-guard(30時間) と訓練(3日) が起床後ずっと判断されなくなる。
        ok.append(("猶予は短い一定値", 60 <= SETTLE_AFTER_WAKE <= 900))

        # ── 届かなかった知らせを溜める ──
        g._hold("こわれた知らせ")
        g._hold("こわれた知らせ")
        rows = g._pending()
        ok.append(("届かない知らせを溜める", len(rows) == 1))
        ok.append(("同じ文面はまとめる", rows and rows[0].get("count") == 2))
        for i in range(PENDING_MAX + 10):
            g._hold(f"別の知らせ {i}")
        ok.append(("溜めすぎない", len(g._pending()) <= PENDING_MAX))

        # ── 道具の呼び方（OS で並べ直す）──
        # **Windows は拡張子の無いファイルを直に実行できない。**
        # ここを間違えると、家の道具どうしの呼び出しが WinError 193 で全部落ちる
        # （2026-09-23、実機で claw status がそうなった）。
        道 = os.path.join(tmp, "にせの道具")
        with open(道, "w") as f:
            f.write("#!/usr/bin/env python3\nprint('x')\n")
        本来 = os.name
        try:
            # **両方の OS を明に試す。**「いまの OS が POSIX である」を前提にすると、
            # Windows で走らせた日にこの試験自身が落ちる（2026-09-23 に踏んだ）。
            os.name = "posix"
            ok.append(("POSIX では並べ直さない",
                       道具の呼び方([道, "--check"]) == [道, "--check"]))
            os.name = "nt"
            包んだ = 道具の呼び方([道, "--check"])
            ok.append(("Windows では python で包む",
                       len(包んだ) == 3 and 包んだ[0] == sys.executable
                       and 包んだ[1] == 道 and 包んだ[2] == "--check"))
            ok.append(("拡張子があるものは触らない",
                       道具の呼び方(["node.exe", "x"]) == ["node.exe", "x"]))
            ok.append(("そもそも無いものは触らない",
                       道具の呼び方(["/無い/道具"]) == ["/無い/道具"]))
        finally:
            os.name = 本来

        # ── 予算: うるさい見張りに財布を全部使わせない ──
        #
        # **財布は家じゅうで1つ。**同じ文面で鳴き続ける相手が1本いるだけで、
        # 本物の警報が黙って捨てられる（2026-09-23、5:30 の訓練の赤が実際に落ちた）。
        # 繰り返しは先に止め、**初めて出た顔のぶんだけ取り置く**。
        # **通るべき側（本物が届く）と止める側（繰り返しが止まる）の両方を見る。**
        送った箱 = []
        g3 = Guard("予算の試験")
        g3.log_path = os.path.join(LOG_DIR, "予算の試験.log")
        g3.state_path = os.path.join(tmp, "予算-state.json")
        g3.lock_path = os.path.join(tmp, "予算.lock")
        g3._post = lambda tok, ch, t: (送った箱.append(t), True)[1]
        _env = globals()["env_value"]
        globals()["env_value"] = lambda k: "x"
        # **訓練中でも、この検査だけは本物の道を通す。**
        # 訓練の印があると notify は送らずに帰るので、印を見たままだと
        # 「初めての知らせが通る」は環境のせいで必ず落ちる（2026-09-23 に踏んだ）。
        _mark = DRILL_MARK   # global 宣言は上の「訓練中の行」の検査で済んでいる
        DRILL_MARK = os.path.join(tmp, "訓練の印は無い")
        try:
            for _ in range(送信の予算 * 2):
                g3.notify("同じ顔の知らせ")
            繰り返し = len([t for t in 送った箱 if "同じ顔" in t])
            g3.notify("初めて出た知らせ（本物の警報のつもり）")
            初めて届いた = any("初めて出た" in t for t in 送った箱)
        finally:
            globals()["env_value"] = _env
            DRILL_MARK = _mark
        ok.append(("繰り返しに財布を使い切らせない", 繰り返し <= 送信の予算 - 取り置き))
        ok.append(("初めて出た知らせは取り置きで通る", 初めて届いた))
        ok.append(("捨てた知らせは中身ごと残る",
                   len(g3.捨てた知らせ()) >= 送信の予算 and
                   all(行 for _t, _見, 行 in g3.捨てた知らせ())))

        # ── 同じ話を二度言わない（保存が先） ──
        st = {}
        g.notify = lambda t: None       # 送る所は試さない
        first = g.tell_once(st, "k", "一度だけ")
        second = g.tell_once(st, "k", "一度だけ")
        ok.append(("一度言ったら二度言わない", first is True and second is False))
        ok.append(("言う前に覚え書きを保存する", g.load_state().get("k") is True))

        # ── 落ちても心拍は残る ──
        os.unlink(os.path.join(PULSE_DIR, "selftest.json"))
        g2 = Guard("selftest2")
        g2.log_path = os.path.join(LOG_DIR, "selftest2.log")
        g2.state_path = os.path.join(tmp, "selftest2-state.json")
        g2.notify = lambda t: None
        g2.quiet_crash = True           # 検査のときだけ、わざと落とした跡を画面に出さない
        rc = g2.run(lambda: (_ for _ in ()).throw(RuntimeError("わざと落とす")))
        ok.append(("落ちても心拍は残る", pulse_age("selftest2") is not None))
        ok.append(("落ちたことは失敗として返す", rc == 1))
        ok.append(("落ちたことを記録に残す",
                   "落ちた" in open(g2.log_path).read()))
        rc2 = g2.run(lambda: 0)
        ok.append(("普通に終われば戻り値をそのまま返す", rc2 == 0))

        # ── 蹴る予算 ──
        atomic_write(KICK_FILE, json.dumps(
            {"ai.openclaw.zzz-not-real": datetime.now().isoformat(timespec="seconds")}))
        how, _ = kickstart("ai.openclaw.zzz-not-real")
        ok.append(("さっき蹴った相手は見送る", how == "waiting"))
        how2, _ = kickstart("ai.openclaw.zzz-not-real", min_gap=0)
        # 仕組みそのものが無い機械では「仕組みなし」と答える。**どちらも「蹴った」ではない。**
        ok.append(("居ない相手は失敗と答える（成功と嘘をつかない）",
                   how2 in ("failed", "仕組みなし")))

        # ── 他人が書いているログの切り詰め ──
        big = os.path.join(tmp, "big.log")
        with open(big, "w") as f:
            for i in range(200000):
                f.write(f"{i} " + "x" * 60 + "\n")
        before_size = os.path.getsize(big)
        # 開いたまま掴んでいる側がいても、同じファイルであり続けること
        holder = open(big, "a")
        before_ino = os.stat(big).st_ino
        trimmed = trim_file(big, max_bytes=1024 * 1024, keep_bytes=256 * 1024)
        ok.append(("大きすぎるログを切り詰める",
                   trimmed and os.path.getsize(big) < before_size))
        ok.append(("書いている側のファイルを取り替えない（差し替えない）",
                   os.stat(big).st_ino == before_ino))
        holder.write("あとから書いた行\n")
        holder.close()
        ok.append(("切り詰めたあとも書き込みが残る",
                   "あとから書いた行" in open(big).read()))
        ok.append(("小さいログには触らない",
                   trim_file(big, max_bytes=100 * 1024 * 1024) is False))

        # 走っている相手に手を出さないこと。これが 2026-08-31 の蹴り合いの芯なので、
        # 本物の常駐（gateway）で確かめる。予算を使う前に返るので、何も起きない。
        running, _secs = _job_state("ai.openclaw.gateway")
        if running:
            how3, _ = kickstart("ai.openclaw.gateway", min_gap=0)
            ok.append(("走っている相手は蹴らない", how3 == "running"))
        else:
            ok.append(("走っている相手は蹴らない（いま常駐が無いので見送り）", True))
    finally:
        (OPENCLAW, PULSE_DIR, LOG_DIR, PENDING_FILE, KICK_FILE,
         BUDGET_FILE, DROPPED_FILE) = keep
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for n, r in ok if not r]
    for n, r in ok:
        print(f"  {'ok  ' if r else 'NG  '}{n}")
    print(f"\n  {len(ok) - len(bad)} / {len(ok)} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
