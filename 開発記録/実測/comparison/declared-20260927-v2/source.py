#!/usr/bin/env python3
"""guardrun — AI の仕事を、壁の中で走らせて、外側から採点する。

## 何を前提にしているか

**嘘と沈黙。** この2つは、モデルが賢くなれば減るという性質のものではない。

  嘘   2026-09-10、qwc は自分で grep して0件を見たうえで、別のファイルを
       書き換えて「削除しました」と報告した。画面の文字は正常に見える。
  沈黙 この家のものは落ちずに黙る。config-guard は「戻した」と言って
       戻していなかった。qwc-guard は毎朝 exit127 で、誰も気づかなかった。

**そして壁自身も黙って壊れる。** sandbox-exec は Apple が非推奨にしている。
OS を上げた日に効かなくなっても、エラーも警報も出ない。ただ素通しになって、
走っているものは全部成功する。**「壁がある」と思っている状態が一番危ない。**

## だから6つに分ける

    契約   どこに書ける・どこへ出られる・いくつまで・何秒まで
           → ただの値。どの機械でも同じ
    予告   走り出す前に置く「まだ終わっていない」
           → ただのファイル。どの機械でも同じ
    受領証 前と後の差分の計算。**モデルの文章は1文字も入れない**
           → ただの算術。どの機械でも同じ
    証明   脱出を試みて失敗することを、対照つきで見せる
           → 形は同じ。期待する結果が執行ごとに違うだけ
    ---- ここから下だけが機械ごとに違う ----
    窓口   機械にだけ聞けること（起動時刻・プロセス表・cwd）
           → macOS は sysctl+ps+lsof、Linux は /proc、無い機械もある
    執行   実際に縛る道具。**重ねられる**
           → 囲い: macOS は sandbox-exec、Linux は bwrap
           → 境界: 別ユーザ（uid を分ける）。囲いの代わりではなく下に敷く

**移せないのは下の2つだけ。** しかも役割が違う：

    嘘への備え（受領証）      算術。**どこでも同じに効く**
    沈黙への備え（予告・掃除）ファイルと signal と窓口。**ほぼどこでも効く**
    閉じ込め（場所・秘密・通信・記録）**ここだけが OS の道具に依る**

AIエージェントで困るのは主に嘘と沈黙のほうで、それは閉じ込めが
無くても効く。2026-09-12 に3つの機械で測って、この線引きを確かめた（下）。

## 壁は「通ってくれれば効く」。境界は「通らなくても効く」

2026-09-12 に測って分かった、いちばん大きい線。

    壁の中から受領証に触る    できない（記録 = ○）
    **壁の外から受領証に触る  できた。「中断」を「緑」に書き換えられた**

囲い（sandbox-exec / bwrap）が守るのは**guardrun を通ったものだけ**で、
同じ uid の別のものは受領証を何でも書ける。**これは実装の穴ではなく
uid の意味そのもの**なので、中で頑張っても閉じない。閉じるには uid を分ける。

    uid を分けて測った（Linux・囲いを外して uid だけ）
      記録  ○ 置き場（人の uid・700）は読みも書きも Permission denied
      残党  ○ setsid した孫が `pkill -u` で 1本 → 0本
      場所  ★ /tmp のような誰でも書ける所には書ける
      秘密  ★ **家の 750 は守りにならない**（作業場へ辿り着かせるために
              通り道の穴を自分で開けるので、名前を知っていれば読める）
      通信  ★ uid では止められない

**だから重ねる。**uid が 記録・残党 を、囲いが 場所・秘密・通信 を持つ。
重ねた実測（Linux・別ユーザ + bwrap）は **11項目すべて ○**。
macOS はまだ uid が居ないので 残党 ★ のまま（`guardrun-user-setup` を
1回 sudo で走らせると作られ、そこで verify が答えを出す）。

## 証明できない壁は、無いものとして扱う

require= に挙げた壁が証明できなければ、**走らせない**。
「たぶん効いている」で走らせると、効いていなかった日に何も起きない。

## 実測（2026-09-12・3つの機械で verify() を回した結果）

                      macOS+uid      Linux+bwrap    Linux（道具なし）
    場所              ○              ○              ★ 外に書けた
    秘密              ○ 11件         ○              ★ 288バイト読めた
    通信              ○ 名指し       ○ 全遮断        ★ 縛れない
    量・総量・仕掛け   ○              ○              ○
    CPU・時間         ○              ○              ○
    残党              **○**          **○**          ★
    記録              ○              ○              ★ 偽造できる
    黙り              ○              ○              **○**

    macOS の 残党 は 2026-09-12 に `_guardrun`（uid 450）を作って閉じた。
    sandbox-exec だけでは永久に ★ だった壁で、**閉じたのは uid のほう**。

**いちばん大事なのは最下行。**壁が1枚も無い機械でも、黙って終わった走りは
見つかる。閉じ込めは OS の道具に依るが、**「やったことが消えない」は依らない。**

**残党は Linux のほうが強い。**bwrap の `--unshare-pid` と
`--die-with-parent` で、自分でグループを作った孫も親と一緒に消える。
macOS の sandbox-exec にはこれに当たるものが無い（専用ユーザが要る）。
**移植は「同じことができるか」ではなく、「どちらが何を守れるか」を出す作業。**

**通信の形が違う。**macOS は行き先ごとに名指しできるが、bwrap は
全遮断しかできない（名指しの穴を開けるには root か中継が要る）。
だから bwrap は**行き先を書いた契約を拒否する**。黙って一部だけ守ると、
契約書に書いてあるのに効いていない、という一番悪い形になる。

**罠: 許可パスは実体パスでないと効かない。**/var/folders（symlink）を渡した
1回目は、許可したはずの中まで全部拒否された。しかもエラー文は
「厳しすぎる」と「甘すぎる」を区別しない。だから real() を必ず通す。

**罠: 一時ファイルのために /private/var/folders を丸ごと許したら、作業場が
その下にあるときに壁ごと素通しになった。**自分で開けた穴を、証明で見つけた。

## 持ち運びについて（正直に）

  実際に走らせた … macOS 15（M5）／Debian 13（Linux 7.0、bwrap あり・なし）
  まだ無い       … Windows の執行と窓口（形がまるで違う。job object と
                   AppContainer。ここは「無い」と書いておく）
                   別ユーザによる執行（macOS の 残党 を塞ぐ唯一の道。
                   作るのに1回だけ管理者権限が要る）
  道具が無い機械 … `require=嘘と沈黙だけ` で走る。**壁は諦めるが、
                   黙って終わる道は塞がる。**諦めたものは受領証に残る

**2台目に移して初めて見つかった穴が4つある。**1台では原理的に見えない：

  1. 執行が1つも起動しないのに、通信と CPU が ○ になっていた
     （何も走らなければ「外に出られない」も「2秒で終わった」も真になる）
  2. ゾンビを生き残りと数えていた（macOS は launchd がすぐ拾うので出ない。
     **親を待たない親**の下では、死んだ走りが永久に「走行中」に見えた）
  3. 秘密の試験が、本人の ~/.ssh が在ることに頼っていた
     （真っさらな機械では13件すべて「無い」で、何も確かめられない）
  4. `/usr/bin/python3` と `lsof` と `ps -axo` の決め打ち
     （debian:slim の python は /usr/local/bin にある）

**移植は機能追加ではなく、試験である。**

**書いていないものを「対応」と書かない。**執行を足したら、まず
verify() が通ることを見せる。通らないものは入れない。
"""

import hashlib
try:
    import pwd
except ImportError:                      # Windows
    pwd = None
import json
import os
import platform
try:
    import ctypes           # Windows の管理者判定にだけ使う
except ImportError:
    ctypes = None
import re
# **POSIX にしか無いものは、無くても読み込めるようにする。**
#
# 2026-09-14 実測：Windows に無いものを隠して読ませたら、guardrun.py の
# `import resource`（139行目）で止まった。**壁の話に到達すらしない。**
# 「壁が効かない」と「読み込めない」はまったく別の失敗で、後者は
# **何が効かないのかを答えることすらできない**——いちばん役に立たない壊れ方。
#
# 無いなら無いと答えられる形にする。Windows の CPU は見届け役の Job で縛る。
# 量は rlimit が無ければ効かず、verify の量が実測で ★ を出すので、
# **こちらで「たぶん効かない」と書く必要は無い。**
try:
    import resource
except ImportError:                      # Windows
    resource = None
import shutil
import stat
import signal
import subprocess
import sys
import tempfile
import threading
try:
    import fcntl
    msvcrt = None
except ImportError:                      # Windows
    try:
        import msvcrt                    # 鍵はこちらで掛ける
    except ImportError:
        msvcrt = None
    fcntl = None
import time

HOME = os.path.expanduser("~")

# **道具の在り処は機械ごとに違う。**debian:bookworm-slim には `ps` すら
# 入っていない（2026-09-12 実測）。決め打ちにすると、移した先で
# 「壁が効かない」ではなく**「試験が走らない」形で黙る**——どちらも
# 結果は同じ（誰も確かめていない状態）だが、後者は原因が見えにくい。
PY = sys.executable or shutil.which("python3") or "/usr/bin/python3"
CURL = shutil.which("curl")
WINDOWSか = platform.system() == "Windows"

# **文字の取り決めを機械任せにしない。**Windows の既定は cp1252 で、
# 日本語を1文字でも書こうとすると UnicodeEncodeError で落ちる。
# 2026-09-23 実測：囮の秘密を置く1行（`開く(囮,"w")`）で証明が止まり、
# **壁の話に到達すらしなかった。**`import resource` で止まった Linux と
# 同じ形（壁が効かないのではなく、試験が走らない）。
# 環境変数（PYTHONIOENCODING）に頼ると、**人が打つときだけ落ちる**ので、
# 自分で決める。読み書きは次の2つを必ず通す。
for _流れ in (sys.stdout, sys.stderr):
    try:
        _流れ.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def 開く(path, mode="r", **kw):
    """テキストの読み書きは必ずここを通す。**utf-8 を明に言う。**"""
    if "b" not in mode:
        kw.setdefault("encoding", "utf-8")
    return open(path, mode, **kw)


def _自分のuid():
    """自分の uid。**Windows には uid が無い**ので、その旨を返す。

    受領証の記名（誰が採点したか）に使う。名前が無いより、
    「uid の無い機械の、この利用者」と書けるほうが後から追える。"""
    if hasattr(os, "getuid"):
        # **ここは os.getuid() のまま。**2026-09-23 の Windows 対応で os.getuid() を
        # 一括で _自分のuid() に置き換えたとき、この行まで置き換わり、POSIX では
        # 呼ぶたびに自分を呼び続けて RecursionError で落ちていた（証明を使う本番の道だけ。
        # 印の試験も訓練も prove=False で、この道を通っていなかった）。2026-09-24 guardrun-実測 で発見。
        return str(os.getuid())     # 指紋に混ぜるので文字列（元は str(os.getuid())）
    return "uidなし:" + (os.environ.get("USERNAME") or "?")


def _根か():
    """管理者として動いているか。**POSIX の uid 0 に当たるもの。**"""
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0
    try:
        return bool(ctypes and ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# **CPU 上限で殺されたときの番号。**Windows にこの signal は無い
# （rlimit ごと無い）。`signal.SIGXCPU` を直に書くと、そこに来た走りが
# 全部 AttributeError で落ちる——2026-09-23 に実際そうなった。
_XCPU = getattr(signal, "SIGXCPU", None)
_XFSZ = getattr(signal, "SIGXFSZ", None)


def _強く殺す():
    """いちばん強い止め方。**Windows に SIGKILL は無い。**"""
    return getattr(signal, "SIGKILL", signal.SIGTERM)


class 小仕事:
    """証明の中で走らせる**小さな命令**を作る。

    **ここが移植の要だった。**2026-09-23 まで、証明の中身は 23 か所すべて
    `/bin/sh -c "…"` で書いてあった。Windows に `/bin/sh` は無いので、
    verify は最初の「執行が動くか」で落ちて **12項目すべて ★**（実測では
    そこにも届かず 0.5 秒で例外）だった。**壁が張れるか以前に、測る道具が
    動かない。**壁を書く前にここを直さないと、何を足しても測れない。

    POSIX 側は実績のある `/bin/sh` のまま残す（macOS の 12○ を壊さない）。
    Windows では**同じ効果**を python の一行で書く。
    **同じ文字列を両方で動かそうとしない。**`echo x > a.txt` は cmd では
    空白の扱いが違って黙って化けるし、`seq` も `chmod` も無い。
    「同じ命令が動く」ではなく「**同じことが起きる**」を揃える。"""

    @staticmethod
    def _py(コード):
        return [PY, "-c", コード]

    @staticmethod
    def _sh(命令):
        return ["/bin/sh", "-c", 命令]

    @classmethod
    def 声(cls):
        """走ったことが分かるだけの命令。**執行が動くかの土台。**"""
        if WINDOWSか:
            return cls._py("print('ok')")
        return cls._sh("echo ok")

    @classmethod
    def 書く(cls, 先, 中身="ok"):
        if WINDOWSか:
            return cls._py("open(r%r,'w').write(%r)" % (先, 中身))
        return cls._sh("echo %s > %s" % (中身, 先))

    @classmethod
    def 読む大きさ(cls, 先):
        """読めたバイト数を数字だけ出す。**読めなければ 0。**

        判定側は「数字が返らない＝試験が成立していない」と読むので、
        ここでは必ず数字だけを出すこと。"""
        if WINDOWSか:
            return cls._py(
                "import os,sys\n"
                "p=r%r\n"
                "n=0\n"
                "try:\n"
                "    if os.path.isdir(p):\n"
                "        for f in os.listdir(p)[:50]:\n"
                "            try: n+=len(open(os.path.join(p,f),'rb').read())\n"
                "            except Exception: pass\n"
                "    else: n=len(open(p,'rb').read())\n"
                "except Exception: n=0\n"
                "print(n)" % 先)
        if os.path.isdir(先):
            return cls._sh("cat %s/* 2>/dev/null | wc -c" % 先)
        return cls._sh("cat %s 2>/dev/null | wc -c" % 先)

    @classmethod
    def 家の外の見本(cls):
        """壁の外に在って、ふつうなら読めるもの。**通るべき側の対照。**"""
        if WINDOWSか:
            return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                "System32", "notepad.exe")
        return "/usr/bin/env"

    @classmethod
    def 続けて増やす(cls):
        """止まらずに増やし続ける。**見回りが止められるかを測る。**"""
        if WINDOWSか:
            return cls._py(
                "import time\n"
                "i=0\n"
                "while True:\n"
                "    i+=1\n"
                "    open('f%d.txt'%i,'w').write('x')\n"
                "    time.sleep(0.05)")
        return cls._sh("i=0; while :; do i=$((i+1)); echo x > f$i.txt; "
                       "sleep 0.05; done")

    @classmethod
    def まとめて増やす(cls, 数, 頭="f"):
        """一気に増やす。**見回りでは間に合わない速さ。**"""
        if WINDOWSか:
            return cls._py("for i in range(1,%d+1): open('%s%%d.txt'%%i,'w').write('x')"
                           % (数, 頭))
        return cls._sh("for i in $(seq 1 %d); do echo x > %s$i.txt; done"
                       % (数, 頭))

    @classmethod
    def 書いて消す(cls):
        if WINDOWSか:
            return cls._py("import os\nopen('a.txt','w').write('x')\nos.unlink('a.txt')")
        return cls._sh("echo x > a.txt; rm a.txt")

    @classmethod
    def 何もしない(cls):
        if WINDOWSか:
            return cls._py("pass")
        return cls._sh("true")

    @classmethod
    def 即終わる(cls):
        """起動してすぐ終わるだけ。**ゾンビの見本を作る。**"""
        if WINDOWSか:
            return cls._py("pass")
        return cls._sh("exit 0")

    @classmethod
    def 孫を残す(cls, 印, 組を抜ける=False, 親の待ち=30, 孫の待ち=3):
        """親が殺されても動く孫を作らせる。**始末が届くかを測る。**

        POSIX は fork + setsid。Windows に fork は無いので
        `DETACHED_PROCESS`（親から切り離して起動）で同じ形にする。
        **組を抜ける／抜けないの違いは Windows には無い**ので、
        抜ける側だけが作れる——それは「この機械では2つを測り分けられない」
        ということなので、そう分かる形で返す。"""
        if WINDOWSか:
            切り離す = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
            孫 = ("import subprocess,sys,time\n"
                  "subprocess.Popen([sys.executable,'-c',"
                  "\"import time;time.sleep(%d);open(r%r,'w').write('x')\"],"
                  "creationflags=%d)\n"
                  "time.sleep(%d)" % (孫の待ち, 印, 切り離す, 親の待ち))
            return cls._py(孫)
        体 = ("os.setsid(), " if 組を抜ける else "")
        return cls._sh(
            PY + ' -c "import os,time;os.fork() or (%s'
            "time.sleep(%d), open('%s','w').write('x'), os._exit(0))\""
            " ; sleep %d" % (体, 孫の待ち, 印, 親の待ち))

    @classmethod
    def 書いて孫を残す(cls, 組を抜ける=True, 親の待ち=30, 孫の待ち=90):
        """1つ書いてから、組を抜ける孫を残して固まる。**黙りの見本。**"""
        if WINDOWSか:
            切り離す = 0x00000008 | 0x00000200
            return cls._py(
                "import subprocess,sys,time\n"
                "open('a.txt','w').write('x')\n"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(%d)'],"
                "creationflags=%d)\n"
                "time.sleep(%d)" % (孫の待ち, 切り離す, 親の待ち))
        体 = ("os.setsid(), " if 組を抜ける else "")
        return cls._sh(
            "echo x > a.txt; " + PY + ' -c "import os,time;'
            "os.fork() or (%stime.sleep(%d), os._exit(0))\"; sleep %d"
            % (体, 孫の待ち, 親の待ち))

    @classmethod
    def 居座る(cls, 親の待ち=90, 孫の待ち=90):
        """作業場を掴んだまま残る孫。**掃除が見つけられるかの見本。**"""
        if WINDOWSか:
            切り離す = 0x00000008 | 0x00000200
            return cls._py(
                "import subprocess,sys,time\n"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(%d)'],"
                "creationflags=%d)\n"
                "time.sleep(%d)" % (孫の待ち, 切り離す, 親の待ち))
        return cls._sh(PY + ' -c "import os,time;os.fork() or '
                       '(os.setsid(), time.sleep(%d), os._exit(0))" ; sleep %d'
                       % (孫の待ち, 親の待ち))

    @classmethod
    def 組を抜けた孫を測れるか(cls):
        """`setsid` した孫と、ふつうの孫を**測り分けられる**機械か。

        Windows にプロセス組は無い。測り分けられないのに2回測ると、
        同じものを2回測って「両方 ○」と書くことになる。"""
        return not WINDOWSか

    @classmethod
    def 誰でも書ける所(cls):
        """**本当に誰でも書ける所**を1つ作って返す。

        POSIX は `/tmp` の下に 777 で作る。Windows の `chmod` は
        ほぼ何もしないので、それでは**管理者の一時置き場**（他人は
        そもそも入れない）を作ってしまい、**壁が無くても ○ に見える。**
        だから Windows では実際に誰でも書ける Windows\\Temp の下に作る。"""
        if WINDOWSか:
            公 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")
            先 = os.path.join(公, "guardrun-誰でも-%d" % os.getpid())
            os.makedirs(先, exist_ok=True)
            return 先
        先 = tempfile.mkdtemp(prefix="guardrun-誰でも-")
        os.chmod(先, 0o777)
        return 先

    @classmethod
    def 走る道具を置く(cls, 先):
        """「あとで壁の外で走るもの」を置く。**仕掛けの見本。**

        POSIX は `#!/bin/sh` と実行ビット。Windows に実行ビットは無いので、
        拡張子（.cmd）で同じ意味になる。"""
        if WINDOWSか:
            return cls._py("open(r%r,'w').write('@echo off\\n')" % (先 + ".cmd"))
        return cls._sh("echo '#!/bin/sh' > %s && chmod +x %s" % (先, 先))

# 壁の名前。**require= で名指しするのはこれ。**
場所, 秘密, 通信, 量, 総量, CPU, 時間, 残党, 仕掛け, 記録, 黙り = (
    "場所", "秘密", "通信", "量", "総量", "CPU", "時間", "残党", "仕掛け",
    "記録", "黙り")
# **壁ではなく、受領証が嘘をつかないかの見分け。**だから ALL_WALLS には入れない
# （require= で名指しする対象ではない）。証明では最後に並ぶ。
跡 = "跡"
ALL_WALLS = (場所, 秘密, 通信, 量, 総量, CPU, 時間, 残党, 仕掛け, 記録, 黙り)

# **記録 と 黙り は、壁というより「黙れないようにする仕掛け」である。**
# 記録 … 受領証の置き場に、採点される側の手が届かないこと
# 黙り … 黙って終わった走りが、外側から必ず見つかること
# 前の9つは「悪いことをさせない」、この2つは「起きたことが消えない」。
# **消えないほうが先である。**壁が抜けたことに気づけるのは記録だけなので。

# **仕掛け は壁ではなく採点。**それでも要求に入れる。
# あとで外で走るものを見つけられないまま走らせるのは、
# 壁が無いまま走らせるのと同じだから。採点も黙って壊れる
# （.git を丸ごと除外していた形で、実際に壊れていた）。

# **「量」は1ファイルの大きさしか意味しない。**
# 2026-09-11、65536バイト/ファイルの上限つきで小さいファイルを500個
# 書かせたら、500個とも書けて判定は緑だった。RLIMIT に合計の口は無く
# （soft = 9223372036854775807）、inode 数の口も無い。
# **名前が、防げる範囲より広く聞こえていた。**
# 合計は rlimit では縛れないので、壁時計と同じ「自前で測って殺す」形にする。

# **既定では 残党 を求めない。**この執行では証明できないので、
# 求めると何も走らなくなる。「走りは止める」は約束するが、
# 「何も生き残らない」は約束しない——という線引きを明示する。
既定の要求 = (場所, 秘密, 通信, 量, 総量, 時間, 仕掛け, 記録, 黙り)

# **閉じ込めを諦めた機械のための要求。**
#
# 壁（場所・秘密・通信・記録）は OS の道具がいる。無い機械では証明できず、
# 既定の要求では**何も走らない**。そこで諦めるのは正しくない——
# AIエージェントの困りごとのうち、**嘘と沈黙は閉じ込めとは別の話**だからである。
#
#   嘘   受領証（前と後の差し引き）。ただの算術。**どの機械でも同じ**
#   沈黙 予告と掃除。ファイルと POSIX の signal だけ。**どの機械でも同じ**
#   閉じ込め 場所・秘密・通信・記録。**ここだけ OS ごとに違う**
#
# 2026-09-12 に3つの機械で実測して、この線引きが正しいことを確かめた
# （Linux の container で bwrap を取り上げても、黙り は ○ のままだった）。
#
# **これを使うときは、何を諦めたのかを言うこと。**壁が無い機械では、
# モデルは家じゅうを読めるし、受領証を書き換えることもできる。
# 「やったことが消えない」ではなく「**ふつうに動いた回は、やったことが残る**」
# に落ちる。それでも、黙って終わる道が塞がるだけで拾える事故はある。
嘘と沈黙だけ = (量, 総量, 時間, 仕掛け, 黙り)

# 読めてしまうと困るもの。**執行が対応していなければ、ただの願いになる。**
SECRETS = [
    os.path.join(HOME, ".ssh"),
    os.path.join(HOME, ".aws"),
    os.path.join(HOME, ".gnupg"),
    os.path.join(HOME, "Library", "Keychains"),
    os.path.join(HOME, ".openclaw", ".env"),
    os.path.join(HOME, ".openclaw", "state"),
]

# **名指ししていない家の中のもの。**証明はここも当たる。
# SECRETS を増やす後追いでは終わらないことが 2026-09-11 に分かったので、
# 「家の中は原則読ませない」が効いているかを、名指しの外で確かめる。
家の中の見本 = [
    os.path.join(HOME, ".config", "gh", "hosts.yml"),      # GitHub トークン
    os.path.join(HOME, ".qwythos-code", ".env"),           # Tavily 鍵
    os.path.join(HOME, ".claude.json"),
    os.path.join(HOME, ".zsh_history"),
    os.path.join(HOME, ".gitconfig"),
    os.path.join(HOME, ".openclaw", "openclaw.json"),
]

# 既定の上限。**数字を直接書かず、理由から出す。**
WALL_CLOCK_SEC = 1800              # 30分。qwc の実測が最長で十数分なので倍を見た
CPU_SEC = 1200                     # 前処理は GPU 側。CPU が20分回るのは異常
MAX_FILE_BYTES = 2 * 1024 * 1024   # 1ファイル2MB。この家のソースは最大 60KB 程度
MAX_OPEN_FILES = 512
# 1回の走りで作業場に増やしてよい量。**理由から出す。**
# この家のソースは ~/コーディングCLI 全部で 411ファイル・4.9MB。
# 1回の作業で足すのは数ファイル・数十KB なので、下は3桁の余裕がある。
MAX_ADD_BYTES = 100 * 1024 * 1024
MAX_ADD_FILES = 1000
# 増えかたを見にいく間隔。数えるのは実測 0.01 秒なので安い。
量の見回り秒 = 1.0
# 子が終わったあと、出力を取り切るのを待つ長さ。
# **これは壁時計とは別。**待つ相手を分けないと、パイプを握った孫が
# 壁時計を好きなだけ伸ばせる（2026-09-12 実測で 2秒→25.2秒）。
出力の待ち秒 = 5.0

# **走りごとに「どれだけ増える見込みか」を宣言させる。**
#
# 2つの要求が正面から衝突するため、1つの数字では両立しない：
#   ディスク枯渇を捕まえる → node_modules も数えないといけない
#   npm install を壊さない → node_modules は数えてはいけない
#
# 分ける軸は「大きさ」ではなく **それが期待された増加か** である。
# 既定は厳しく、要るときだけ宣言で緩める。**宣言なき大量増加だけが赤。**
#
# 数字は実測から出す（2026-09-12・この機械の node_modules）：
#   omega-accounting 46,915ファイル/874MB ／ ナレッジ連携基盤 28,132/730MB
# いちばん大きいものの約3倍を見た。上限を跳ね上げるだけの案（10万等）を
# 採らないのは、46,915 が正当である以上、攻撃もその下に収まるからで、
# **それは穴を広げるだけ**になる。宣言が要るからこそ意味がある。
増加の宣言 = {
    "ふつう":       (MAX_ADD_BYTES, MAX_ADD_FILES),
    "依存を入れる": (3 * 1024 * 1024 * 1024, 150_000),
}


def 正規化ホーム():
    """SBPL に書くホーム。**firmlink を寄せた形で。**"""
    return SandboxExec.正規化(real(HOME))


class 契約違反(Exception):
    """契約そのものが作れない。**走らせる前に落とす。**"""


# SBPL は規則を1行のテキストで書くので、パスに文字列を閉じる記号が入ると
# **規則をまるごと書き足せる。**2026-09-11、ピアが実際にやって見せた：
#
#   作業場 = /tmp/gq/work")) (allow network-outbound) (allow file-read* (subpath "/x
#   → (allow file-write* (subpath "/private/tmp/gq/work")) (allow network-outbound) …
#   → 通信 deny のはずが example.com に 200（対照＝注入なしは 000）
#
# エスケープもするが、**それより先に弾く。**ふつうの作業場にこの文字は
# 入らないので、入っていること自体が異常である。
# **禁じる文字は OS で違う。**POSIX では `\\` を弾く（sandbox-exec の
# 規則に文字列で入るため）。Windows では `\\` は区切りそのものなので、
# 同じ設定にすると**あらゆるパスが契約違反になる**（2026-09-23、証明が
# contract() の1行で落ちた）。代わりに、起こし役の .ps1 が値を括るのに
# 使う `'` を弾く。**「同じ規則を両方に当てる」ではなく「同じ穴を塞ぐ」。**
危険な文字 = (set('"\'\n\r\x00') if WINDOWSか
              else set('"\\\n\r\x00'))


def 安全なパスか(p):
    return not (set(p) & 危険な文字)


def _shell引用(s):
    """shell に渡す1語を安全に括る。**契約と同じで、まず弾いてから括る。**"""
    return "'" + str(s).replace("'", "'\\''") + "'"


def real(path):
    """実体パスに直す。**執行に渡す前に必ず通す。**

    symlink のまま渡すと、許可したはずの場所まで拒否される。
    エラー文では原因が分からないので、探すのに時間が溶ける。"""
    return os.path.realpath(os.path.expanduser(path))


# ── 契約 ──────────────────────────────────────────────────────

def contract(writes, net=(), secrets=None, reads=(), cpu_sec=CPU_SEC,
             wall_sec=WALL_CLOCK_SEC, max_file_bytes=MAX_FILE_BYTES,
             max_open=MAX_OPEN_FILES, max_add_bytes=MAX_ADD_BYTES,
             max_add_files=MAX_ADD_FILES, 記録=None):
    """走らせてよい範囲。**ただの値。機械に依存しない。**"""
    悪い = [p for p in list(writes) + list(net) for p in [str(p)]
            if not 安全なパスか(p)]
    if 悪い:
        raise 契約違反("規則を壊す文字が入っている: %s" % "／".join(悪い))
    # **書ける場所と受領証の置き場を重ねない。**（2026-09-24・Codex の監査）
    # 置き場の祖先を書ける場所に入れると、Mac では読みの禁止しか効かず、中の命令が
    # 受領証の置き場に書けた（実走: 置き場に 偽.txt を置けたうえ、受領証は「青」）。
    根 = 記録の根(記録)
    重なり = [real(p) for p in writes
              if real(p) == 根 or 根.startswith(real(p) + os.sep) or real(p).startswith(根 + os.sep)]
    if 重なり:
        raise 契約違反("書ける場所が受領証の置き場（%s）と重なっている: %s" % (根, "／".join(重なり)))
    return {
        "書ける場所": [real(p) for p in writes],
        "出られる先": list(net),
        # **受領証の置き場は、必ず読ませない側に入れる。**
        # 既定では家の中なので上の deny で塞がるが、置き場を家の外に
        # 移されたときに黙って読めるようになる。名指ししておけば移動に付いてくる。
        "読ませない": [real(p) for p in (SECRETS if secrets is None else secrets)]
                      + [記録の根(記録)],
        # **読みも許可制にする。**名指しの deny だけだと、名指ししていない
        # ものが全部読める。2026-09-11 実測で ~/.config/gh/hosts.yml（GitHub
        # トークン）・~/.qwythos-code/.env（Tavily 鍵）・~/.claude.json ほか
        # 6件が壁の中から素で読めた。SECRETS を増やすのは後追いで終わらない。
        # 家の中は原則読ませず、要るものだけ名指しする形に変える。
        "読める場所": [real(p) for p in writes] + [real(p) for p in reads],
        "CPU秒": cpu_sec,
        "壁時計秒": wall_sec,
        "1ファイル上限": max_file_bytes,
        "開けるファイル数": max_open,
        "増やせるバイト": max_add_bytes,
        "増やせるファイル数": max_add_files,
    }


# ── 執行 ──────────────────────────────────────────────────────

class Enforcer:
    """縛る道具。**機械ごとに違うのはここだけ。**

    足すときは name / 使えるか / 囲う / 縛れる壁 の4つを書き、
    verify() が通ることを見せてから入れる。"""

    name = "?"
    縛れる壁 = ()
    # 通信をどの細かさで縛れるか。"名指し"＝行き先ごと／"全遮断"＝全部止めるだけ。
    # **細かさは執行の性質であって、契約の希望ではない。**
    通信の粒度 = "名指し"

    def 使えるか(self):
        return False

    def 子のuid(self):
        """子を別の uid で走らせるなら (uid, gid)。しないなら None。

        **これは「囲う」では書けない。**exec の前に落とすものなので、
        argv をいじる話ではない。"""
        return None

    def 用意(self, c, workdir, tmproot):
        """走る前に要る下ごしらえ。→ (できた, 理由)

        別 uid にすると、作業場と一時置き場に**その uid が入れない**
        （家は 750 なので通り道すら無い）。**穴は最小で開ける。**"""
        return True, ""

    def 片付け(self, c, workdir, tmproot):
        """用意で開けた穴を閉じる。**閉じ忘れは壁が1枚減ったのと同じ。**"""

    def 本人の物を消す(self, tmproot):
        """一時置き場の中で、壁の中の本人にしか消せない物を消させる。**既定は何もしない。**"""

    def 環境を直す(self, env, tmproot):
        """子に渡す環境をこの執行に合わせる。**既定は何もしない。**"""
        return env

    def 要る書き場(self):
        """この執行で走らせるために、どうしても書けないといけない所。

        **契約に足すので受領証に出る。**黙って広げない。"""
        return ()

    def 子のumask(self):
        """子に掛ける umask。None なら触らない。

        別 uid で走らせると、**agent が作ったファイルは agent の持ち物**に
        なる。既定の umask 022 だと 644 で、人は読めても**書き換えられない**
        （2026-09-14 実測：`メモ.md _guardrun:wheel` に人が追記できなかった）。
        持ち主を後から変える道は無い（chown には root が要る）ので、
        **group に書ける形で作らせる**しかない。"""
        return None

    def 一時の親(self):
        """一時置き場をどこに作るか。None なら機械の既定。

        別 uid で走らせるときは、既定（macOS の `/var/folders/…/T`）が
        **持ち主しか通れない 700** なので、中に穴を開けても辿り着けない。
        **通り道の穴を増やすより、通れる所に置くほうが穴が少ない。**"""
        return None

    def 殺す(self, pid):
        """1本だけ殺す。**人の権限で届かないときの逃げ道。**"""
        return False

    def 皆殺し(self):
        """その走りのものを全部殺す。できない執行は None を返す。

        **`kill -u` は組を抜けた孫にも届く。**killpg で届かないものが
        居なくなるのはここだけ（2026-09-12、Linux で 1→0 本を実測）。"""
        return None

    def 契約を守れるか(self, c):
        """この執行で、その契約をそのまま守れるか。→ (守れる, 理由)

        **守れないなら走らせない。**黙って一部を捨てて走らせるのが
        いちばん悪い（契約書には書いてあるのに、効いていない）。
        たとえば bwrap は「ollama にだけ出てよい」を作れないので、
        出先を書いた契約は拒否する。全部塞いでよいなら走る。"""
        if c.get("出られる先") and self.通信の粒度 == "全遮断":
            return False, ("この執行は通信を全部塞ぐことしかできないので、"
                           "行き先を名指しした契約（%s）は守れない。"
                           "壁の外から渡すか、net_allow を空にすること"
                           % "・".join(c["出られる先"]))
        return True, ""

    def 囲う(self, argv, c, tmproot):
        """argv を、この執行で囲んだ argv に変える。"""
        raise NotImplementedError


class SandboxExec(Enforcer):
    """macOS の sandbox-exec（Seatbelt）。**Apple は非推奨にしている。**

    非推奨でも、いま効くことは実測した。効かなくなる日は黙って来るので、
    verify() を毎回通す前提で使う。"""

    name = "sandbox-exec (macOS)"
    縛れる壁 = (場所, 秘密, 通信)
    BIN = "/usr/bin/sandbox-exec"

    def 使えるか(self):
        return platform.system() == "Darwin" and os.path.exists(self.BIN)

    @staticmethod
    def 逃がす(path):
        """SBPL の文字列に入れる前に記号を殺す。**弾くほうが本命で、これは保険。**"""
        return path.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def 正規化(path):
        """macOS の firmlink を、SBPL が見るのと同じ側に寄せる。

        **2026-09-11 実測。**/Users/USER/.ssh と
        /System/Volumes/Data/Users/USER/.ssh は同じ実体（16777229:1012876）だが、
        os.path.realpath はどちらもそのまま返す。SBPL は**正規の側
        （/Users/…）で判定する**ので、

            deny を /Users/USER/.ssh           に書く → 両方の道から塞がる
            deny を /System/Volumes/Data/…      に書く → **両方の道から読める**

        後者は**エラーも警告も出さない。**プロファイルは正常に読み込まれ、
        書いた本人は壁があると思っている。いちばん危ない壊れ方なので、
        ここで寄せる。ただし寄せるだけでは足りないので、verify() が
        1件ずつ効いていることを別に確かめる。"""
        prefix = "/System/Volumes/Data"
        if path.startswith(prefix + "/"):
            return path[len(prefix):]
        return path

    def 規則(self, c, tmproot):
        # 既定は deny。**許したものだけが通る**ので、書き忘れは
        # 「動かない」側に倒れる。逆にすると素通しになって気づけない。
        lines = [
            "(version 1)",
            "(deny default)",
            "(allow process-exec process-fork signal)",
            "(allow sysctl-read)",
            "(allow mach-lookup)",
            "(allow file-read*)",
            # **家の中は原則読ませない。**下で名指ししたものだけ戻す。
            '(deny file-read* (subpath "%s"))' % 正規化ホーム(),
            # **家そのものの stat だけは通す（中身は見せない）。**
            # 2026-09-14、作業場が家の中にある本物の repo で走らせたら、
            # node が起動前に落ちた:
            #   EPERM: operation not permitted, lstat '/Users/USER'
            # スクリプトの実体パスを解くのに**通り道の各段を lstat** するため。
            # `literal` なので**家の1段だけ**——中の名前を数えることも、
            # 中のファイルの大きさを見ることもできない
            # （`subpath` にすると ~/.ssh/id_rsa の有無や大きさが漏れる）。
            '(allow file-read-metadata (literal "%s"))' % 正規化ホーム(),
            "(allow file-ioctl)",
            '(allow file-write-data (literal "/dev/null") (literal "/dev/stdout") '
            '(literal "/dev/stderr") (literal "/dev/dtracehelper"))',
        ]
        for p in list(c["書ける場所"]) + [tmproot]:
            lines.append('(allow file-write* (subpath "%s"))' % self.逃がす(real(p)))
        # 名指しで読ませるものを戻す（家の中でも通す）
        for p in list(c["読める場所"]) + [tmproot]:
            lines.append('(allow file-read* (subpath "%s"))'
                         % self.逃がす(self.正規化(real(p))))
        for t in c["出られる先"]:
            lines.append('(allow network-outbound (remote ip "%s"))' % self.逃がす(t))
        # **外を名指ししたときだけ、名前を引く道を開ける。**（2026-09-25・未踏⑥）
        # macOS の DNS は mDNSResponder の UNIX ソケットを通る。IP の行き先だけ開けても名前が引けず、
        # 外の API に出るエージェント（Codex・Claude Code）は壁の中で1歩も出られなかった（壁の中の curl が終了コード6）。
        # ollama だけの走り（qwc など）は今までどおり名前を引けない＝外の名前も調べられない。
        if any(t.split(":")[0] not in ("localhost", "127.0.0.1", "::1") for t in c["出られる先"]):
            lines.append('(allow network-outbound (remote unix-socket (path-literal "/private/var/run/mDNSResponder")))')
        # **規則は後に書いたほうが勝つ。**秘密の拒否は最後に置く。
        for p in c["読ませない"]:
            lines.append('(deny file-read* (subpath "%s"))' % self.逃がす(self.正規化(real(p))))
        return "\n".join(lines) + "\n"

    def 囲う(self, argv, c, tmproot):
        fd, pf = tempfile.mkstemp(suffix=".sb", dir=tmproot)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.規則(c, tmproot))
        return [self.BIN, "-f", pf] + list(argv)


class Bubblewrap(Enforcer):
    """Linux の bubblewrap。**macOS の sandbox-exec に当たるもの。**

    考え方は同じ（既定で塞ぎ、名指しで戻す）だが、**通信だけは形が違う。**

        macOS   行き先ごとに名指しで開けられる（remote ip "..."）
        Linux   `--unshare-net` は**ループバックごと全部閉じる**。
                名指しの穴を開けるには root か、slirp のような中継が要る。

    だから 通信の粒度 を "全遮断" と申告し、行き先を書いた契約は
    **拒否する**（契約を黙って一部だけ守るより、走らせないほうがよい）。
    **これは弱点であると同時に、設計の指針でもある**——モデルに
    ネットを触らせず、必要な通信は壁の外の呼び出し側が行う形なら、
    こちらのほうが強い（穴が1つも無い）。

    `--die-with-parent` があるので、**親が死んだときの残党は macOS より少ない**
    （それでも掃除は要る。bwrap ごと SIGKILL された場合は届かない）。"""

    name = "bwrap (Linux)"
    縛れる壁 = (場所, 秘密, 通信)
    通信の粒度 = "全遮断"

    def _bin(self):
        return shutil.which("bwrap")

    def 使えるか(self):
        """**置いてあるかではなく、立つかを見る。**（2026-09-24・M9）
        Ubuntu 24.04 の特権なし（AppArmor が非特権の名前空間を止める）や、特権なしのコンテナでは
        bwrap は置いてあるのに立たない。前は置いてあるだけで選び、別ユーザ+bwrap の走りが全部
        拒否になり、証明は 12★「執行が1つも走らない」だった（--privileged なしの Docker で再現）。
        本番と同じ旗で1回だけ試し、立たなければ使わない（理由は 立たない理由 に残して証明に出す）。"""
        if platform.system() != "Linux" or not self._bin():
            return False
        global _bwrapの試し
        if _bwrapの試し is None:
            try:
                r = subprocess.run([self._bin(), "--ro-bind", "/", "/", "--proc", "/proc",
                                    "--dev", "/dev", "--unshare-net", "--unshare-ipc",
                                    "--unshare-uts", "--unshare-pid", "--die-with-parent", "true"],
                                   capture_output=True, text=True, timeout=15)
                _bwrapの試し = (r.returncode == 0,
                                 (r.stderr or r.stdout or "終了コード %d" % r.returncode).strip()[:200])
            except Exception as ex:                      # noqa: BLE001
                _bwrapの試し = (False, "%s: %s" % (type(ex).__name__, ex))
        return _bwrapの試し[0]

    def 立たない理由(self):
        return None if _bwrapの試し is None or _bwrapの試し[0] else _bwrapの試し[1]

    def 囲う(self, argv, c, tmproot):
        家 = real(HOME)
        cmd = [self._bin(), "--die-with-parent",
               # 既定は「全部あるが、書けない」。書ける所だけ下で開ける。
               "--ro-bind", "/", "/",
               "--proc", "/proc", "--dev", "/dev",
               "--unshare-net", "--unshare-ipc", "--unshare-uts", "--unshare-pid"]
        # **家の中は丸ごと隠す。**名指しの deny を並べる形は後追いで終わらない
        # （2026-09-11、名指ししていない6件が素で読めた）。
        if os.path.isdir(家):
            cmd += ["--tmpfs", 家]
        # 名指しで読ませるものを戻す
        for p in list(c["読める場所"]) + [tmproot]:
            cmd += ["--ro-bind-try", real(p), real(p)]
        # 書ける場所（読みも当然できる）
        for p in list(c["書ける場所"]) + [tmproot]:
            cmd += ["--bind-try", real(p), real(p)]
        # **家の外に置かれた秘密も塞ぐ。**家を隠しただけでは足りない。
        for p in c["読ませない"]:
            p = real(p)
            if os.path.isdir(p):
                cmd += ["--tmpfs", p]
            elif os.path.exists(p):
                cmd += ["--ro-bind", "/dev/null", p]
        # **かぶせた一時領域は、最後に読み取り専用にする。**（2026-09-24・母艦）
        # --tmpfs は書ける。家や秘密のフォルダに書くと成功して見え、走りが終わると
        # 消えていた（GitHub ubuntu-22.04 で実測: /home/runner/外.txt が 書けた=True・
        # 終了0・外には残らない）。**命令は書けたと思い込む**＝嘘の報告の種になる。
        # Mac（sandbox-exec）はここで EPERM を返すので、Linux だけが違っていた。
        # 下に重ねた bind（書ける場所・読める場所）は別のマウントなので、そのまま効く。
        # 壁の中の道具の /Users/USER は一時置き場（書ける）を指すので、道具の書き物は困らない。
        for p in ([家] if os.path.isdir(家) else []) + [
                real(p) for p in c["読ませない"] if os.path.isdir(real(p))]:
            cmd += ["--remount-ro", p]
        return cmd + ["--"] + list(argv)


class 別ユーザ(Enforcer):
    """走りを別の uid にする。**壁ではなく、OS の境界そのもの。**

    ## なぜこれが要るのか（2026-09-12 の実測）

    sandbox-exec と bwrap の壁は本物だが、**guardrun を通ったものにしか
    効かない。**同じ uid で動く別のものは、受領証を何でも書き換えられる。
    実測: 壁の外から `"判定": "中断"` を `"緑"` に書き換えられた
    （壁の中からは読めない＝verify の 記録 は ○ なのに、である）。
    **これは実装の穴ではなく uid の意味そのもの**なので、中では閉じない。

    Linux（root を持てる container）で測った結果：

        受領証（人の uid・700）  別 uid からは読めも書けもしない
        setsid した孫           `pkill -u` で 1本 → 0本
        作業場（通るべき側）      書ける

    ## 何を縛れて、何を縛れないか

        縛れる   秘密（家は 750 なので一歩も入れない）
                 記録（置き場が 700 なら偽造できない）
                 残党（`kill -u` が全部に届く）
        縛れない 場所（/tmp のような誰でも書ける所には書ける）
                 通信（uid では止められない）

    **だから単体では使わない。**sandbox-exec / bwrap と重ねる（`重ね`）。
    足りない壁は verify が ★ で出すので、黙って通ることはない。

    ## まだ確かめていないこと

    **macOS では未検証。**この機械にはまだ `_guardrun` が居ない
    （`guardrun-user-setup` を1回 sudo で走らせると作られる）。
    居ない間 `使えるか()` は False なので、選ばれることは無い。
    居るようになった日に、verify が本当に効くかどうかを答える。"""

    name = "別ユーザ (uid 分離)"
    # **秘密 は入れない。**作業場へ辿り着かせるために `~` へ通り道
    # （search）の穴を自分で開けるので、名前を知っているファイルは
    # 読めてしまう（2026-09-12、Linux で囮の秘密を 288 バイト読まれた。
    # 家の 750 を、こちらの用意が壊していた）。
    # **読みの壁は囲い（sandbox-exec / bwrap）が持つ。**重ねれば ○ になる。
    縛れる壁 = (記録, 残党)
    通信の粒度 = "縛れない"

    def __init__(self, 利用者=None):
        self.利用者 = 利用者 or os.environ.get("GUARDRUN_USER", "_guardrun")
        self._uid = None

    def _引く(self):
        if self._uid is None:
            try:
                if pwd is None:
                    raise KeyError("この機械には pwd が無い")
                p = pwd.getpwnam(self.利用者)
                self._uid = (p.pw_uid, p.pw_gid)
            except (KeyError, ImportError):
                self._uid = (None, None)
        return self._uid

    def 使えるか(self):
        uid, _gid = self._引く()
        if uid is None or uid == os.getuid():
            return False
        if _根か():
            return True            # 自分で落とせる（sudo は要らない）
        # 人として動いているなら、合言葉なしで成れるかを実際に試す
        sudo = shutil.which("sudo")
        if not sudo:
            return False
        try:
            return subprocess.run([sudo, "-n", "-u", self.利用者, "/usr/bin/true"],
                                  capture_output=True, timeout=20).returncode == 0
        except Exception:
            return False

    def 子のuid(self):
        uid, gid = self._引く()
        return (uid, gid) if (uid is not None and _根か()) else None

    def 囲う(self, argv, c, tmproot):
        if _根か():
            return list(argv)      # uid と umask は preexec で掛ける
        # **`sudo` は自前の umask（既定 0022）をかぶせる。**preexec_fn で
        # `os.umask(0o002)` を掛けても打ち消され、agent の作ったファイルが
        # 644 になって**人が書き換えられない**（2026-09-14 実測）。
        # sudoers に `Defaults umask=0002` を足す道もあるが、管理者権限が
        # もう一度要る。**中で掛け直せば要らない。**
        # **`sudo` は環境を捨てる（env_reset）。**2026-09-14 実測：
        # 中から見ると `HOME` だけ残り（macOS の sudoers が env_keep している）、
        # `TMPDIR` も `GIT_CONFIG_GLOBAL` も空だった。`--preserve-env` は
        # sudoers 側の許可が要るので、**中の shell で入れ直す**ほうが確実で、
        # 権限も増やさない。umask も同じ理由でここで掛けている。
        u = self.子のumask()
        前置き = []
        if u is not None:
            前置き.append("umask %04o" % u)
        前置き.append("export TMPDIR=%s" % _shell引用(tmproot))
        前置き.append("export TMP=%s" % _shell引用(tmproot))
        前置き.append("export GIT_CONFIG_GLOBAL=%s"
                      % _shell引用(os.path.join(tmproot, ".gitconfig")))
        中 = ["/bin/sh", "-c", "; ".join(前置き) + '; exec "$@"', "sh"] + list(argv)
        return [shutil.which("sudo"), "-n", "-u", self.利用者, "--"] + 中

    # ── 穴を最小で開ける ──────────────────────────────
    # **足した権利の文字列は、外すときに一字一句同じものが要る。**
    # 1か所に置いて両方から使う（別々に書くと、片方だけ直した日に外れ残る）。
    通り道の権 = "search"
    読む権 = "read,execute,search,file_inherit,directory_inherit"
    行き先の権 = ("read,write,append,search,delete,add_file,"
                  "add_subdirectory,delete_child,file_inherit,"
                  "directory_inherit")

    def _権(self, 種):
        """種: "通り道"（通るだけ）／"読む"（読めるだけ）／"書く"（読み書き）"""
        return {"通り道": self.通り道の権, "読む": self.読む権}.get(
            種, self.行き先の権)

    def _許す(self, path, 種):
        """その uid に、この1つのディレクトリへの権利を足す。→ できたか

        **行き先は中身にも配る（-R）。**ディレクトリに足すだけだと、
        **これから作るものにしか効かない**（file_inherit は新規のみ）。
        既にある `package.json` を書き換えられず、2026-09-12 の証明で
        「仕掛けを見つけられない」と出た——実際には**直せなかった**のだった。
        既存の repo を触らせる道具でこれは致命的なので、中身にも配る。"""
        if platform.system() == "Darwin":
            規則 = "user:%s allow %s" % (self.利用者, self._権(種))
            # まず本体。**ここが通らなければ本当に駄目。**
            ok = subprocess.run(["chmod", "+a", 規則, path],
                                capture_output=True).returncode == 0
            if ok and 種 != "通り道" and os.path.isdir(path):
                # 中身にも配る。**ただし失敗は許す。**
                # 2度目の走りでは、中身に**agent が作ったファイル**が混ざる。
                # それは agent の持ち物なので人からは ACL を付け直せず、
                # `chmod -R` は必ず 0 以外を返す。**そこで用意ごと失敗させると、
                # 2回目から全部の壁が落ちる**（2026-09-12 に実際そうなった）。
                # 付け直せないファイルは、そもそも agent が書けるので要らない。
                subprocess.run(["chmod", "-R", "+a", 規則, path],
                               capture_output=True)
            return ok
        setfacl = shutil.which("setfacl")
        if not setfacl:
            return False
        権 = {"通り道": "x", "読む": "rx"}.get(種, "rwx")
        # **その場所そのものへの付与だけを成否に使う。**中身への再帰は失敗を許す。（2026-09-24）
        # 前の走りで agent が作ったファイルは、人の側から setfacl できない（持ち主が違う）。
        # `-R` の失敗で用意ごと落としていたので、**同じ作業場の2回目は必ず拒否**になり、
        # 証明は 6★（秘密・量・CPU・時間・残党・黙り）だった（GitHub ubuntu-22.04 で実測・Codex の仮説）。
        # Mac の chmod +a と同じ扱い：付け直せないファイルは、そもそも agent が書ける。
        ok = subprocess.run([setfacl, "-m", "u:%s:%s" % (self.利用者, 権), path],
                            capture_output=True).returncode == 0
        if ok and 種 != "通り道":
            subprocess.run([setfacl, "-R", "-m", "u:%s:%s" % (self.利用者, 権), path],
                           capture_output=True)
        return ok

    def _外す(self, path, 種):
        """足した権利だけを、名指しで外す。

        **番号で外してはいけない（`chmod -a# 0`）。**2026-09-12、走らせる前に
        気づいた：この家の `~` には元から `group:everyone deny delete` が
        0番に入っており、こちらが足したものは 1番に入る（実測）。
        番号で外すと**人の守りを消す**。同じ文字列で名指しして外す。"""
        if platform.system() == "Darwin":
            規則 = "user:%s allow %s" % (self.利用者, self._権(種))
            subprocess.run(["chmod", "-a", 規則, path], capture_output=True)
            if 種 != "通り道" and os.path.isdir(path):
                subprocess.run(["chmod", "-R", "-a", 規則, path],
                               capture_output=True)
        else:
            setfacl = shutil.which("setfacl")
            if setfacl:
                subprocess.run([setfacl, "-x", "u:%s" % self.利用者, path],
                               capture_output=True)

    def 用意(self, c, workdir, tmproot):
        """作業場と一時置き場だけ開ける。**通り道は search だけ。**

        家は 750 なので、開けないと作業場にも辿り着けない。
        だが家ごと開けてはいけない（それでは uid を分けた意味が消える）。
        **通り道には通る権利だけ、行き先には読み書き**を足す。"""
        self._開けた = []      # [(path, 種)]。外すときに同じ権利の文字列が要る
        # **通れない所だけ開ける。**家の中だけを見ていたのでは足りない
        # （作業場が /private/tmp/claude-xxx のような 700 の下にあることがある）。
        # 逆に、既に誰でも通れる所（/private/tmp は 1777）には何もしない。
        # 開ける権利は search だけ＝**中身を並べることも読むこともできない**。
        # **契約に書いた場所すべてに、uid の側でも道を開ける。**
        # 壁（sandbox）が「読んでよい」と言っても、**uid が入れなければ読めない。**
        # 2026-09-14、`~/コーディングCLI` を読める契約にしたのに node が
        # モジュールを解決できずに落ちた——家が 750 で agent が通れなかったため。
        # **2層あることを忘れると、どちらか片方だけ直して直った気になる。**
        # **agent 自身の持ち物には穴を開けない（開けられない）。**
        # `要る書き場` で足した砂場は agent のものなので、人からは chmod できず、
        # ここで失敗して**走り全部が拒否になる**（2026-09-14 に踏んだ）。
        # 元から入れる場所に鍵を掛け直そうとしていた、というだけの話。
        自前 = {real(p) for p in self.要る書き場()}
        行き先 = [(real(p), "書く") for p in list(c["書ける場所"]) + [tmproot]
                  if real(p) not in 自前]
        行き先 += [(real(p), "読む") for p in c["読める場所"]
                   if real(p) not in {x for x, _ in 行き先} | 自前]
        道 = []
        for 先, _種 in 行き先:
            p = os.path.dirname(先)
            while p and p != "/":
                try:
                    通れる = bool(os.stat(p).st_mode & 0o001)
                except OSError:
                    通れる = True      # 見えないものには手を出さない
                if not 通れる and p not in 道:
                    道.append(p)
                p = os.path.dirname(p)
        for d in 道:
            if self._許す(d, "通り道"):
                self._開けた.append((d, "通り道"))
            else:
                return False, "通り道に穴を開けられない（%s）" % d
        for 先, 種 in 行き先:
            if not os.path.exists(先):
                continue               # 無いものには開けようがない
            if self._許す(先, 種):
                self._開けた.append((先, 種))
            else:
                return False, "%s に穴を開けられない（%s）" % (種, 先)
        # **git に「持ち主が違うのは承知の上」と伝える。**
        # uid を分けると repo の持ち主（人）と走る側（agent）がずれるので、
        # git は `fatal: detected dubious ownership` で全部断る（実測）。
        # **身元（user.name/email）は書かない。**commit は、受領証を読んだ
        # 人がやること——agent の名前で歴史に入れない。
        try:
            with 開く(os.path.join(tmproot, ".gitconfig"), "w") as f:
                f.write("[safe]\n\tdirectory = %s\n" % real(workdir))
        except OSError:
            pass
        # **作業場の group を、人の主グループに合わせる。**
        # BSD（macOS）では新しいファイルの group は**親ディレクトリから継ぐ**
        # ので、ここを揃えないと umask 002 にしても人の入れない group になる
        # （実測：`_guardrun:wheel` で、daigo は wheel に居ないので書けなかった）。
        # 走り終わったら元に戻す。
        self._元のgid = None
        try:
            st = os.stat(real(workdir))
            if st.st_gid != os.getgid():
                self._元のgid = st.st_gid
                os.chown(real(workdir), -1, os.getgid())
        except OSError:
            pass
        return True, ""

    def 本人の物を消す(self, tmproot):
        """**別 uid が作った物は、その uid に消させる。**（2026-09-24）

        qwc は一時置き場（HOME）の中に `.qwythos-code/sessions` を 0700 で作る。
        持ち主は agent なので人は中を覗けず、`rmtree(ignore_errors=True)` が
        **黙って消し損ねていた**（/private/tmp/guardrun-* が毎朝1個ずつ残った）。
        **ACL を外す前に呼ぶこと。**外したあとでは agent 自身が一時置き場に入れない。"""
        uid, _gid = self._引く()
        sudo = shutil.which("sudo")
        if uid is None or not sudo or _根か():
            return
        try:
            名前 = os.listdir(tmproot)
        except OSError:
            return
        for n in 名前:
            道 = os.path.join(tmproot, n)
            try:
                if os.lstat(道).st_uid != uid:
                    continue
            except OSError:
                continue
            try:
                subprocess.run([sudo, "-n", "-u", self.利用者, "/bin/rm", "-rf", 道],
                               capture_output=True, timeout=60)
            except Exception:                            # noqa: BLE001
                pass

    def 片付け(self, c, workdir, tmproot):
        # **agent が作ったファイルの ACL は、人には外せない**（持ち主が違う）。
        # 実測：走り終わったあとも `メモ.md` に `+` が残っていた。
        # 持ち主になれる相手＝その uid 自身に頼めば外せる。
        sudo = shutil.which("sudo")
        if sudo and not _根か():
            subprocess.run([sudo, "-n", "-u", self.利用者, "/bin/chmod", "-R",
                            "-a", "user:%s allow %s" % (self.利用者, self.行き先の権),
                            real(workdir)], capture_output=True)
        for d, 種 in reversed(getattr(self, "_開けた", [])):
            self._外す(d, 種)
        self._開けた = []
        戻す = getattr(self, "_元のgid", None)
        if 戻す is not None:
            try:
                os.chown(real(workdir), -1, 戻す)
            except OSError:
                pass
            self._元のgid = None

    def 環境を直す(self, env, tmproot):
        """**HOME を一時置き場に向ける。**別 uid の家（/var/empty）は
        書けないので、そのままでは「家に何も書けない」で落ちる道具が出る
        （npm・git・python のキャッシュはどれも HOME を見る）。"""
        env = dict(env)
        env["HOME"] = tmproot
        env["GIT_CONFIG_GLOBAL"] = os.path.join(tmproot, ".gitconfig")
        return env

    def 要る書き場(self):
        """**その uid 自身の一時置き場。**macOS の `git` は xcrun の皮で、
        `TMPDIR` を見ずに `confstr(_CS_DARWIN_USER_TEMP_DIR)` に書きにいく。
        塞いだままだと `git: error: couldn't create cache file … (errno=
        Operation not permitted)` で git がまるごと使えない（2026-09-14 実測）。

        **uid ごとに別の道**なので、人の側（`/var/folders/lv/…`）は塞がったまま。
        広げるのは agent 自身の砂場だけ。

        **作業場がその下にあるときは足さない。**一時置き場のために
        `/private/var/folders` を丸ごと許して壁ごと素通しにした前科がある。"""
        d = self._一時()
        if not d:
            return ()
        return (d,)

    def _一時(self):
        try:
            o = subprocess.run(
                [shutil.which("sudo") or "/usr/bin/sudo", "-n", "-u", self.利用者,
                 "/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"]
                if not _根か() else ["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            d = (o.stdout or "").strip().rstrip("/")
            return d if d.startswith("/var/folders/") else None
        except Exception:
            return None

    def 子のumask(self):
        return 0o002        # 664 で作らせる（人が同じ group なら書き換えられる）

    def 一時の親(self):
        """**誰でも通れる所に置く。**`/var/folders/…/T` は 700 なので、
        そこに tmproot を作ると別 uid は sandbox の規則ファイルすら開けない
        （2026-09-12 実測: `sandbox-exec: …/tmpxxx.sb: Permission denied`）。
        `/private/tmp` は 1777（誰でも通れる・消せるのは持ち主だけ）なので、
        **通り道の穴を1つも開けずに**置ける。置き場自体は 700＋ACL で守る。"""
        for d in ("/private/tmp", "/tmp"):
            if os.path.isdir(d):
                return d
        return None

    def 殺す(self, pid):
        """その uid のものを1本だけ殺す。→ 殺せたか

        **人からは別 uid のプロセスに signal が届かない**（Operation not
        permitted）。uid を分けた副作用で、掃除が残党を始末できなくなる
        （2026-09-12 実測: pid 83611/83614 が残った）。
        **その uid になってから殺せば届く**——`皆殺し` と違って、
        同時に走っている別の走りを巻き込まない。"""
        sudo = shutil.which("sudo")
        if not sudo:
            return False
        try:
            return subprocess.run(
                [sudo, "-n", "-u", self.利用者, "/bin/kill", "-9", str(pid)],
                capture_output=True, timeout=20).returncode == 0
        except Exception:
            return False

    def 皆殺し(self):
        """その uid のものを全部殺す。**組を抜けた孫にも届く。**

        **同じ uid で同時に走っている別の走りも巻き込む。**いまは1本ずつ
        走らせる前提でよいが、並べて走らせるなら走りごとに uid を分けること
        （そこまでは作っていない。ここに書いておく）。"""
        uid, _gid = self._引く()
        if uid is None:
            return None
        pkill = shutil.which("pkill")
        if not pkill:
            return None
        引数 = [pkill, "-9", "-u", str(uid)]
        if not _根か():
            sudo = shutil.which("sudo")
            if not sudo:
                return None
            引数 = [sudo, "-n", "-u", self.利用者] + 引数
        try:
            r = subprocess.run(引数, capture_output=True, text=True, timeout=20)
        except Exception:
            return False
        # **打てたかを見る。**（2026-09-24）前は終了コードを見ずに毎回 1 を返していたので、
        # sudo が断っても「殺した」と同じ顔だった。pkill は 0=殺した・1=居なかった、それ以外と
        # sudo の断りは失敗。
        if r.returncode in (0, 1) and "sudo:" not in (r.stderr or ""):
            return 1
        return False


class 重ね(Enforcer):
    """執行を重ねる。**外側が uid、内側が囲い。**

    `sudo -u _guardrun sandbox-exec -f 規則 命令` の形になる。
    片方で足りない壁を、もう片方が埋める：

        別ユーザ     秘密・記録・残党（uid の境界）
        sandbox-exec 場所・秘密・通信（囲い）

    **執行は1つに絞るものではない。**どちらが何を守るかは verify が
    1件ずつ答えるので、重ねたことで曖昧になる心配は無い。"""

    def __init__(self, 外, 内):
        self.外, self.内 = 外, 内
        self.name = "%s + %s" % (外.name, 内.name)
        self.縛れる壁 = tuple(dict.fromkeys(list(外.縛れる壁) + list(内.縛れる壁)))
        # **通信は実際に縛るほうの粒度を採る。**縛れない側に合わせると、
        # 効いている名指しを「できない」と申告することになる。
        self.通信の粒度 = (内.通信の粒度 if 通信 in 内.縛れる壁
                           else 外.通信の粒度)

    def 使えるか(self):
        return self.外.使えるか() and self.内.使えるか()

    def 子のuid(self):
        return self.外.子のuid() or self.内.子のuid()

    def 囲う(self, argv, c, tmproot):
        return self.外.囲う(self.内.囲う(argv, c, tmproot), c, tmproot)

    def 用意(self, c, workdir, tmproot):
        for e in (self.内, self.外):
            ok, なぜ = e.用意(c, workdir, tmproot)
            if not ok:
                return ok, なぜ
        return True, ""

    def 片付け(self, c, workdir, tmproot):
        for e in (self.外, self.内):
            e.片付け(c, workdir, tmproot)

    def 本人の物を消す(self, tmproot):
        for e in (self.外, self.内):
            e.本人の物を消す(tmproot)

    def 環境を直す(self, env, tmproot):
        for e in (self.内, self.外):
            env = e.環境を直す(env, tmproot)
        return env

    def 一時の親(self):
        for e in (self.外, self.内):
            d = e.一時の親()
            if d:
                return d
        return None

    def 子のumask(self):
        for e in (self.外, self.内):
            u = e.子のumask()
            if u is not None:
                return u
        return None

    def 要る書き場(self):
        出 = []
        for e in (self.外, self.内):
            出 += list(e.要る書き場())
        return tuple(出)

    def 皆殺し(self):
        for e in (self.外, self.内):
            n = e.皆殺し()
            if n is not None:
                return n
        return None

    def 殺す(self, pid):
        return any(e.殺す(pid) for e in (self.外, self.内))

    def 契約を守れるか(self, c):
        for e in (self.外, self.内):
            ok, なぜ = e.契約を守れるか(c)
            if not ok:
                return ok, なぜ
        return True, ""


class 素通し(Enforcer):
    """何も囲わない。**「囲っていない」と正直に言うためだけに在る。**

    執行が無い機械で黙って素通しにすると、いちばん危ない状態
    （壁があると思っている状態）になる。だから執行として明示する。
    CPU は rlimit／Windows Job、時間は見回りで掛かる。
    量は rlimit のある機械でだけ効く。"""

    name = "素通し（囲っていない）"
    縛れる壁 = ()

    def 使えるか(self):
        return True

    def 囲う(self, argv, c, tmproot):
        return list(argv)


class Windows別ユーザ(Enforcer):
    r"""Windows。**別のローカル利用者にして、ACL と firewall で囲む。**

    ## 材料を1つずつ測ってから書いた（2026-09-23・windows-2025）

        別の利用者を作る            できた（New-LocalUser）
        その人として走らせる        できた（Start-Process -Credential）
        作業場の外に書く            止まった（NTFS の ACL）
        本人の秘密を読む            止まった（Access is denied）
        その人だけ外向きを止める    止まった（SID を書いた規則で 000）
        まとめて始末                1 → 0（taskkill /F /T /FI USERNAME）
        壁の中で python が走る      できた（証明の中身を動かすのに要る）

    **測ってから書く順にしたのは、使えない道具の上に設計すると全部
    無駄になるから。**macOS のときは sandbox-exec を書いてから uid を
    足したが、閉じたのは uid のほうだった。

    ## macOS / Linux と違うところ

        組（process group）が無い   `killpg` に当たるものが無い。
                                    まとめて止めるのは**利用者ごと**。
        実行ビットが無い            仕掛けの見本は拡張子（.cmd）で置く。
        既定拒否の囲いが無い        sandbox-exec / bwrap に当たるものが
                                    標準では無い。**場所は列挙式**——
                                    誰でも書ける所（C:\Windows\Temp など）を
                                    名指しで塞ぐ。塞ぎ漏らした所には書ける。
                                    **「既定で全部禁止」ではないと言っておく。**
        rlimit が無い               Windows には1ファイルの大きさの上限が無い
                                    （Job Object にも無い）。量は **★ のまま出す。**
                                    CPU は別利用者の見届け役から Job で縛る。

    ## 合言葉

    別の人として起こすには合言葉が要る（`sudo -n` に当たるものが無い）。
    `--壁の利用者を作る` が作り、**人だけが読める場所**に置く。
    壁の中からは読めない（読めたら壁の意味が無いので、証明が毎回見る）。"""

    name = "別ユーザ (Windows)"
    # **場所 を入れているのは、公共の書き場を名指しで塞ぐから。**
    # 塞ぎ漏らしがあれば証明の「誰でも書ける所」が ★ にする。
    縛れる壁 = (記録, 残党, 秘密, 場所, 通信)
    # **loopback は Windows の firewall が触れない。**規則をどう書いても
    # 127.0.0.1 は通る。だから「外は全部止まるが、頭脳には届く」になる。
    # これは 全遮断 でも 名指し でもない**第3の粒度**なので、そう申告する。
    # 全遮断 と書くと「localhost も塞がっている」という意味になり、
    # 証明がそれを確かめて ★ にする（2026-09-23、実際にそうなった。
    # **壁の性能ではなく、申告が実物と違っていた。**）。
    通信の粒度 = "loopbackだけ"

    公共の書き場 = (r"C:\Windows\Temp", r"C:\Users\Public")

    def __init__(self, 利用者=None):
        self.利用者 = 利用者 or os.environ.get("GUARDRUN_USER", "guardrun")
        self.合言葉の置き場 = os.path.join(HOME, ".guardrun", "壁の合言葉")
        self._作業場 = None
        self._開けた = []
        self._塞いだ = []
        self._規則 = None
        self._sid値 = None

    # ── 下調べ ──────────────────────────────────────────
    def _合言葉(self):
        try:
            return 開く(self.合言葉の置き場).read().strip()
        except OSError:
            return None

    def _pwsh(self):
        """**pwsh 7 を先に探す。**5.1 が自分のモジュールを読めないことがある。

        2026-09-23 実測：windows-2025 の powershell 5.1 で
        `ConvertTo-SecureString` が「モジュールを読み込めない」で落ちた。
        同じ命令が pwsh 7 では通る（材料の測定で確認済み）。
        **同じ名前の道具が2つあり、片方だけ壊れている**ことがある。"""
        return shutil.which("pwsh") or shutil.which("powershell")

    @staticmethod
    def 掃除した環境():
        """PowerShell を起こすときの環境。**親の読み込み先を持ち込まない。**

        2026-09-23 実測：pwsh 7 の中から powershell 5.1 を起こすと、
        `PSModulePath` が 7 のものを指したままで、5.1 が**自分の標準モジュール
        を読めない**（`ConvertTo-SecureString` が「コマンドが無い」になる）。
        道具が無いのではなく、**道具の在り処が親から漏れている**。"""
        env = dict(os.environ)
        env.pop("PSModulePath", None)
        return env

    def _走らす(self, 命令, 待ち=60):
        ps = self._pwsh()
        if not ps:
            return None
        try:
            return subprocess.run([ps, "-NoProfile", "-NonInteractive",
                                   "-Command", 命令],
                                  capture_output=True, text=True,
                                  errors="replace", timeout=待ち,
                                  env=self.掃除した環境())
        except Exception:
            return None

    def _sid(self):
        if self._sid値 is None:
            o = self._走らす("(New-Object System.Security.Principal.NTAccount('%s'))"
                             ".Translate([System.Security.Principal.SecurityIdentifier])"
                             ".Value" % self.利用者)
            値 = (o.stdout or "").strip() if o else ""
            self._sid値 = 値 if 値.startswith("S-1-") else ""
        return self._sid値

    def 使えるか(self):
        if not WINDOWSか or not self._pwsh():
            return False
        if not self._合言葉():
            return False
        return bool(self._sid())

    # ── 穴を開ける・塞ぐ ────────────────────────────────
    def _icacls(self, *引数):
        self._acl出力 = ""
        ic = shutil.which("icacls")
        if not ic:
            self._acl出力 = "icacls が見つからない"
            return False
        try:
            o = subprocess.run([ic] + list(引数), capture_output=True,
                               text=True, errors="replace", timeout=120)
            self._acl出力 = " ".join(((o.stderr or "") + " " +
                                    (o.stdout or "")).split())[:600]
            if not self._acl出力:
                self._acl出力 = "終了コード %s" % o.returncode
            return o.returncode == 0
        except Exception as e:
            self._acl出力 = str(e)[:600]
            return False

    def 用意(self, c, workdir, tmproot):
        self._作業場 = real(workdir)
        self._開けた, self._塞いだ = [], []
        書く先 = list(dict.fromkeys(
            [self._作業場] + [real(p) for p in list(c["書ける場所"]) + [tmproot]]))
        読む先 = [real(p) for p in c["読める場所"] if real(p) not in 書く先]

        def 失敗(何, 要点):
            # **証明の後に権限を失うこともある。**（2026-09-24）
            # 本番の壁を作れなければ止め、途中で開けた穴も残さない。
            理由 = "%s: %s" % (何, 要点 or "コマンドの出力なし")
            self.片付け(c, workdir, tmproot)
            return False, 理由

        # **継承の印 (OI)(CI) はフォルダにだけ付ける。**（2026-09-24・母艦）
        # ファイルに付けると icacls が断り、許可が黙って付かなかった
        # （読める場所にファイルを1つ名指ししても読めない。証明の対照で発見）。
        def 許す(先, 権):
            継承 = "(OI)(CI)" if os.path.isdir(先) else ""
            引数 = [先, "/grant", "%s:%s%s" % (self.利用者, 継承, 権)]
            # **親への許可は必須、既存の子への配布は補助。**（2026-09-24）
            # 作業場・一時置き場を使えることは実行の前提なので、まず親だけを
            # 確かめる。失敗した命令も一部を変更し得るので、実行前に記録する。
            self._開けた.append(先)
            if not self._icacls(*(引数 + ["/Q"])):
                return False
            if os.path.isdir(先):
                # 付け直せない既存ファイルへの /T の失敗は、使える範囲を狭める
                # だけで壁を開かない。親の継承許可は付いているので失敗扱いにしない。
                # 秘密への明示の拒否は、この配布の後で別に成功を確かめる。
                self._icacls(*(引数 + ["/T", "/Q"]))
            return True

        for 先, 権 in [(p, "M") for p in 書く先] + [(p, "RX") for p in 読む先]:
            if not os.path.exists(先):
                if 権 == "M":
                    return 失敗("利用者への許可に失敗 (%s)" % 先, "書く先が存在しない")
                continue
            if not 許す(先, 権):
                return 失敗("利用者への許可に失敗 (%s)" % 先, self._acl出力)
        # **読ませない物は、明示の拒否で塞ぐ。**（2026-09-24・母艦）
        # 前はここで何もしておらず、家の ACL が壁の利用者に何も許していないことに
        # 頼っていた。だから読める場所の許可が秘密に届くと（家ごと許す・/T で下へ配る）、
        # 名指しの秘密までそのまま読めた（証明の対照で実測: .ssh・.aws・.gnupg 等すべて）。
        # **NTFS は明示の拒否を許可より先に評価する**（正規の並び）ので、許可が後から
        # 届いても拒否が勝つ。Mac の「拒否を最後に書く」と同じ二重の守りになる。
        # 無い物には書けないので、証明はそこへ偽物を置いてから測る。
        for 先 in [real(p) for p in c["読ませない"]]:
            if not os.path.exists(先):
                continue
            継承 = "(OI)(CI)" if os.path.isdir(先) else ""
            # **拒否は補助ではなく壁そのもの。**（2026-09-24）
            # 許可が届いている可能性があるので、拒否を付けられなければ走らせない。
            self._塞いだ.append(先)
            if not self._icacls(先, "/deny", "%s:%s(R)" % (self.利用者, 継承), "/Q"):
                return 失敗("読ませない物への拒否に失敗 (%s)" % 先, self._acl出力)
        # **誰でも書ける所を名指しで塞ぐ。**sandbox-exec のような既定拒否が
        # 無いので、ここは列挙になる。**塞ぎ漏らしは証明が見つける。**
        for 先 in self.公共の書き場:
            if not os.path.isdir(先):
                continue
            # ここも拒否が無ければ外に書けるので、成功が必須。（2026-09-24）
            self._塞いだ.append(先)
            if not self._icacls(先, "/deny", "%s:(OI)(CI)(W,DC)" % self.利用者, "/Q"):
                return 失敗("公共の書き場への拒否に失敗 (%s)" % 先, self._acl出力)
        # **通信は SID を書いた規則で止める。**利用者名では規則に書けない。
        sid = self._sid()
        if not sid:
            return 失敗("Firewall 規則の作成に失敗", "利用者の SID を取得できない")
        self._規則 = "guardrun-%d" % os.getpid()
        # **規則が無ければ外へ通信できるので成功が必須。**（2026-09-24）
        # PowerShell の継続可能なエラーも終了失敗にする。作成途中の失敗でも
        # 規則が残り得るので、名前は片付けが済むまで消さない。
        o = self._走らす(
            "$ErrorActionPreference = 'Stop'; "
            "New-NetFirewallRule -DisplayName '%s' -Direction Outbound "
            "-Action Block -LocalUser \"D:(A;;CC;;;%s)\" -ErrorAction Stop | Out-Null"
            % (self._規則, sid))
        if o is None or o.returncode != 0:
            要点 = ("PowerShell を実行できない、または実行が中断した" if o is None else
                    " ".join(((o.stderr or "") + " " + (o.stdout or "")).split())[:600]
                    or "終了コード %s" % o.returncode)
            return 失敗("Firewall 規則の作成に失敗", 要点)
        return True, ""

    def 片付け(self, c, workdir, tmproot):
        for 先 in self._開けた:
            self._icacls(先, "/remove:g", self.利用者, "/T", "/Q")
        for 先 in self._塞いだ:
            self._icacls(先, "/remove:d", self.利用者, "/Q")
        self._開けた, self._塞いだ = [], []
        if self._規則:
            self._走らす("Remove-NetFirewallRule -DisplayName '%s' "
                         "-ErrorAction SilentlyContinue" % self._規則)
            self._規則 = None
        self.皆殺し()

    def 契約を守れるか(self, c):
        出先 = list(c.get("出られる先") or [])
        外 = [x for x in 出先
              if not x.split(":")[0] in ("localhost", "127.0.0.1", "::1")]
        if 外:
            return False, ("この執行は外向きを全部止めることしかできない"
                           "（loopback は Windows の firewall が触らないので"
                           "頭脳には届く）。行き先を名指しした契約（%s）は守れない"
                           % "・".join(外))
        return True, ""

    # ── 走らせる ────────────────────────────────────────
    def 囲う(self, argv, c, tmproot):
        """別の人として起こす。**引数は JSON で渡す（引用符で化けさせない）。**

        PowerShell の `-ArgumentList` は配列を文字列に組み直すので、
        改行や引用符を含む `python -c "…"` は黙って化ける。
        **道具に引数を解釈させない。**渡すのは2つの道（JSON と起こし役）だけ。"""
        命令の道 = os.path.join(tmproot, "命令.json")
        with 開く(命令の道, "w") as f:
            json.dump(list(argv), f)
        起こし役 = os.path.join(tmproot, "起こし役.py")
        with 開く(起こし役, "w") as f:
            f.write("import json,subprocess,sys\n"
                    "argv=json.load(open(sys.argv[1],encoding='utf-8'))\n"
                    "sys.exit(subprocess.call(argv))\n")
        出 = os.path.join(tmproot, "出.txt")
        誤 = os.path.join(tmproot, "誤.txt")
        走らせ役 = os.path.join(tmproot, "走らせ役.ps1")
        with 開く(走らせ役, "w") as f:
            f.write(
                "$ErrorActionPreference='Stop'\n"
                "$合 = (Get-Content -Raw '%s').Trim()\n"
                "$pw = ConvertTo-SecureString $合 -AsPlainText -Force\n"
                "$cred = New-Object System.Management.Automation.PSCredential("
                "'%s',$pw)\n"
                "$p = Start-Process -FilePath '%s' -ArgumentList '%s','%s' "
                "-Credential $cred -WorkingDirectory '%s' "
                "-RedirectStandardOutput '%s' -RedirectStandardError '%s' "
                "-PassThru -Wait -WindowStyle Hidden\n"
                "if (Test-Path '%s') { Get-Content -Raw '%s' }\n"
                "if (Test-Path '%s') { Get-Content -Raw '%s' }\n"
                "exit $p.ExitCode\n"
                % (self.合言葉の置き場, self.利用者, PY, 起こし役, 命令の道,
                   self._作業場 or os.getcwd(), 出, 誤, 出, 出, 誤, 誤))
        return [self._pwsh(), "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", 走らせ役]

    # ── 止める ──────────────────────────────────────────
    def 殺す(self, pid):
        tk = shutil.which("taskkill")
        if not tk:
            return False
        try:
            return subprocess.run([tk, "/F", "/PID", str(pid)],
                                  capture_output=True, timeout=30).returncode == 0
        except Exception:
            return False

    def 皆殺し(self):
        """その利用者のものを全部止める。**`kill -u` に当たるもの。**

        2026-09-23 実測：親を待たずに数えた残党 1 → まとめて殺した後 0。"""
        tk = shutil.which("taskkill")
        if not tk:
            return None
        try:
            o = subprocess.run([tk, "/F", "/T", "/FI",
                                "USERNAME eq %s" % self.利用者],
                               capture_output=True, text=True,
                               errors="replace", timeout=60)
            return ("SUCCESS" in (o.stdout or "")) or o.returncode == 0
        except Exception:
            return None


囲いたち = [SandboxExec(), Bubblewrap()]
ENFORCERS = 囲いたち + [別ユーザ(), Windows別ユーザ(), 素通し()]


_bwrapの試し = None      # (立ったか, 立たなかった理由)。1つのプロセスで1回だけ試す


def 囲いの見送り():
    """置いてあるのに立たなかった囲いの理由の一覧（証明の見出しに出す）。"""
    出 = []
    for e in 囲いたち:
        f = getattr(e, "立たない理由", None)
        if f and f():
            出.append("%s は置いてあるが立たない（%s）" % (e.name, f()))
    return 出


def pick_enforcer():
    """この機械で使える執行を選ぶ。**必ず何か返る（最後は素通し）。**

    **重ねられるなら重ねる。**uid の境界と囲いは守るものが違うので、
    どちらか一方を選ぶ理由が無い（uid だけでは通信と場所が空き、
    囲いだけでは残党と記録が空く）。"""
    if WINDOWSか:
        # **Windows には重ねる相手（既定拒否の囲い）がまだ無い。**
        # 無いものを在るように見せないため、単体で返す。
        win = Windows別ユーザ()
        return win if win.使えるか() else 素通し()
    囲い = next((e for e in 囲いたち if e.使えるか()), None)
    uid = 別ユーザ()
    if uid.使えるか():
        return 重ね(uid, 囲い) if 囲い else uid
    return 囲い or 素通し()


# ── 証明 ──────────────────────────────────────────────────────

def _probe(enforcer, argv, c, cwd, tmproot):
    """証明用の小さな実行。受領証は作らない。"""
    env = dict(os.environ)
    env["TMPDIR"] = env["TMP"] = env["TEMP"] = tmproot
    env = enforcer.環境を直す(env, tmproot)
    できた, なぜ = enforcer.用意(c, cwd, tmproot)
    if not できた:
        return -1, "下ごしらえができない: %s" % なぜ
    # **Windows は初回が遅い。**別の人として初めて起こすときに利用者の
    # プロファイルが作られる（実測で十数秒）。20秒だと、壁が効いているのに
    # 「執行が1つも走らない」と出る。**遅いことと、動かないことは別。**
    待ち = 90 if WINDOWSか else 20
    try:
        p = subprocess.run(enforcer.囲う(argv, c, tmproot), cwd=cwd, env=env,
                           capture_output=True, text=True, errors="replace",
                           timeout=待ち, stdin=subprocess.DEVNULL,
                           **_子の起こし方(c, enforcer))
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as ex:
        # **命令の全文を返さない。**呼び出し側は先頭200字しか出さないので、
        # 長い argv を返すと**時間切れだったことが画面から消える**
        # （2026-09-23、11項目すべてが同じ切れ方で読めなかった）。
        出 = (ex.stdout or b"")[-200:]
        if isinstance(出, bytes):
            出 = 出.decode("utf-8", "replace")
        return -1, "時間切れ（%d秒）%s" % (待ち, 出)
    except Exception as e:
        return -1, "%s: %s" % (type(e).__name__, e)
    finally:
        enforcer.片付け(c, cwd, tmproot)


def _掃除(base, 日数=1):
    """落ちた証明が置いていった作業場を片付ける。

    走りごとに作る以上、殺された走りのぶんは残る。**新しいものには触らない**
    （いま走っている別の証明の作業場を消すと、こちらが加害者になる）。
    """
    限界 = time.time() - 日数 * 86400
    try:
        for 名 in os.listdir(base):
            if not 名.startswith("run-"):
                continue
            道 = os.path.join(base, 名)
            try:
                if os.path.getmtime(道) < 限界:
                    shutil.rmtree(道, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


class 証明が取れない(RuntimeError):
    """先に走っている証明が終わらなかった。**★ではない。測っていないだけ。**"""


def _鍵を取る(base, 待つ秒=600):
    """証明は一度に1つ。**場所を分けるだけでは足りない。**

    2026-09-13、作業場を走りごとに分けたあとも同時実行で ★ が出続けた。
    量×2・時間×2・仕掛け×1（きれいな回もあり、**出る壁が毎回変わる**）。
    原因は執行が機械全体の状態を触ることで、場所の分離では消えない：

      ・別ユーザは、別 uid が通れるように**共有の親ディレクトリの権限を開けて、
        終わりに閉じる**（self._開けた）。片方の片付けが、もう片方の通り道を閉じる。
      ・残党の試験は `pkill -u` を使う。**相手の走りの孫まで巻き込む。**

    だから待たせる。待つのは嘘ではない——測る順番が後になるだけで、測りはする。
    取れなかったときだけ「測っていない」を投げる。**その場合も ★ にはしない。**
    衝突を「壁が無い」と書くと、本物の仕事が止まる。
    """
    os.makedirs(base, exist_ok=True)
    f = 開く(os.path.join(base, ".鍵"), "w")
    if fcntl is None and msvcrt is None:
        # **鍵が無い機械では直列化しない。**「取れた」と嘘をつかず、
        # 取れないまま進む（証明が2つ重なると互いを壊すが、それは
        # 「壁が無い」とは別の話で、verify の結果に嘘は混ざらない）。
        return f
    限界 = time.time() + 待つ秒
    while True:
        try:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return f                      # プロセスが死ねば OS が必ず離す
        except (OSError, BlockingIOError):
            if time.time() >= 限界:
                f.close()
                raise 証明が取れない(
                    f"先に走っている証明が {待つ秒} 秒で終わらなかった。"
                    "測っていない（壁が無いという意味ではない）。")
            time.sleep(1)


# **証明を使い回してよい時間。**
#
# 教義は「証明は毎回」だった。だが実測で約30秒かかる。対話で使う道具の
# 起動に毎回30秒を足すと、**人は壁のある道を使わなくなる**——そして
# 壁の無い道を使う。安全な道が使われないなら、それは安全ではない。
#
# だから期限つきで使い回す。**使い回したことは受領証に必ず書く**
# （`証明の古さ` 秒）。0 にすれば毎回取り直す。
証明の有効期限 = 600
_証明の覚え = {}          # 執行の名前 → (取った時刻, 結果, 指紋)

# **控えはファイルに置く。プロセスの中だけでは効かない。**
#
# 2026-09-14 実測: `qwc -p "2+2は？"` が 41秒・36秒。命令自体は 6.7秒と 2.1秒で、
# 受領証の `証明の古さ` は**2回とも 0**。qwc は1回ごとに立ち上がるので、
# 上の辞書は毎回空だった。つまり期限つきで使い回す設計は書いてあったのに、
# **1手ごとに34秒を払い続けていた。**
#
# これは「速さ」の問題ではなく**壁の生存**の問題である。毎回34秒待たされると
# 人は `--壁なし` を打つ。壁を守るために壁を外す動機を作るのがいちばん悪い形。
_控えの道 = os.path.join(HOME, ".guardrun-verify", "証明の控え.json")


def _証明の指紋(e):
    """**この証明が、いつまで同じ意味を持つか。**

    時間だけで切ると、OS を上げた直後や guardrun.py を書き換えた直後の
    「もう効かないかもしれない壁」を、期限が切れるまで ○ と言い続ける。
    だから実物の指紋も見る——**変わったら期限内でも測り直す。**
    """
    部品 = [e.name, platform.platform(), _自分のuid()]
    try:
        st = os.stat(os.path.abspath(__file__))
        部品.append("%d:%d" % (st.st_mtime_ns, st.st_size))
    except OSError:
        部品.append("?")          # 読めないなら使い回さない側に倒す
    return hashlib.sha256("|".join(部品).encode()).hexdigest()[:16]


def _控えを読む(指紋, 期限):
    try:
        with 開く(_控えの道) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if d.get("指紋") != 指紋:
        return None
    古さ = time.time() - float(d.get("時刻", 0))
    if 古さ < 0 or 古さ >= 期限:      # 時計が戻った場合も測り直す
        return None
    return {k: (bool(v[0]), v[1]) for k, v in (d.get("結果") or {}).items()}, 古さ


def _控えを書く(指紋, 結果):
    """書けなくても走りは止めない（控えは速さのためのものなので）。"""
    try:
        os.makedirs(os.path.dirname(_控えの道), exist_ok=True)
        仮 = _控えの道 + ".tmp"
        with 開く(仮, "w") as f:
            json.dump({"指紋": 指紋, "時刻": time.time(),
                       "結果": {k: [bool(v[0]), v[1]] for k, v in 結果.items()}},
                      f, ensure_ascii=False)
        os.chmod(仮, 0o600)
        os.replace(仮, _控えの道)
    except OSError:
        pass


def 証明を取る(e, 有効期限=None):
    """期限内かつ指紋が同じなら使い回す。→ (結果, 何秒前に取ったか)

    **使い回したことは受領証に必ず出る**（`証明の古さ` 秒）。0 なら取り立て。
    期限を 0 にすれば毎回取り直す。
    """
    期限 = 証明の有効期限 if 有効期限 is None else 有効期限
    指紋 = _証明の指紋(e)
    覚 = _証明の覚え.get(e.name)
    if 覚 and 期限 > 0 and 覚[2] == 指紋 and (time.time() - 覚[0]) < 期限:
        return 覚[1], time.time() - 覚[0]
    if 期限 > 0:
        控 = _控えを読む(指紋, 期限)
        if 控:
            結果, 古さ = 控
            _証明の覚え[e.name] = (time.time() - 古さ, 結果, 指紋)
            return 結果, 古さ
    結果 = verify(e)
    _証明の覚え[e.name] = (time.time(), 結果, 指紋)
    if 期限 > 0:
        _控えを書く(指紋, 結果)
    return 結果, 0.0


# **証明が置く偽の秘密の印。**この文字列で始まる物だけを片付ける（本物には触らない）。
_見本の印 = "guardrun の証明が置いた偽物。消してよい。"
# 中身を持つ「場所」として扱う置き場所（中に偽物を1つ置く）
_場所として置く = (".ssh", ".aws", ".gnupg", "Keychains", "state")


def _見本を置く(先々):
    """無い置き場所にだけ偽物を置く。**在る物には一切触らない。**

    返すのは (パス, 種) の並び。種は "file"（置いた偽物）か "dir"（作った入れ物）。
    片付けは作った順の逆に行う。"""
    置いた = []
    for p in 先々:
        if os.path.lexists(p):
            continue
        名 = os.path.basename(p)
        try:
            作る親 = []
            親 = os.path.dirname(p)
            while 親 and not os.path.lexists(親):
                作る親.append(親)
                親 = os.path.dirname(親)
            for d in reversed(作る親):
                os.mkdir(d, 0o700)
                置いた.append((d, "dir"))
            if 名 in _場所として置く:
                os.mkdir(p, 0o700)
                置いた.append((p, "dir"))
                中 = os.path.join(p, "guardrun-見本")
            else:
                中 = p
            fd = os.open(中, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_見本の印 + "\n" + "x" * 64)
            置いた.append((中, "file"))
        except OSError:
            continue
    return 置いた


def _見本を片付ける(置いた):
    """置いた偽物だけを消す。消せなかった物の名前を返す（黙って残さない）。"""
    残り = []
    for p, 種 in reversed(置いた):
        try:
            if 種 == "file":
                with open(p, encoding="utf-8", errors="replace") as f:
                    頭 = f.read(len(_見本の印))
                if 頭 != _見本の印:
                    残り.append(p + "（印が違うので消さない）")
                    continue
                os.unlink(p)
            else:
                os.rmdir(p)          # 空でなければ失敗する＝他人の物は消さない
        except OSError as ex:
            残り.append("%s（%s）" % (p, ex.__class__.__name__))
    return 残り


def _本番の道で読む(e, 先, work, 記録根, 名):
    """run() の道で `先` を読ませ、読めたバイト数を文字列で返す。**読めなければ "0"。**

    数は作業場の中のファイルに書かせる（run() は出力を返さないので）。
    ファイルが無ければ ""（＝試験が成立していない）を返す。"""
    場 = os.path.join(work, "読む", 名)
    os.makedirs(場, exist_ok=True)
    結果 = os.path.join(場, "n")
    if os.path.exists(結果):
        os.unlink(結果)
    読む = (
        "import os,sys\n"
        "p=sys.argv[1]\n"
        "n=0\n"
        "try:\n"
        "    if os.path.isdir(p):\n"
        "        for f in os.listdir(p)[:50]:\n"
        "            try: n+=len(open(os.path.join(p,f),'rb').read())\n"
        "            except Exception: pass\n"
        "    else: n=len(open(p,'rb').read())\n"
        "except Exception: n=0\n"
        "open('n','w').write(str(n))\n")
    run([PY, "-c", 読む, 先], 場, wall_sec=20, enforcer=e, prove=False, 記録=記録根)
    try:
        with open(結果) as f:
            return f.read().strip()
    except OSError:
        return ""



def verify(enforcer=None, workroot=None):
    """**この機械で、どの壁が本当に効くか。**脱出を試みて確かめる。

    どの項目にも「通るべき側」を入れてある。執行が全部を拒否するように
    壊れたとき、それを合格と読み違えないため。
    （2026-09-11、自分で開けた穴はこの形で見つけた。）

    返すのは {壁: (効いたか, 説明)}。**測れなかったものは False。**
    「たぶん効いている」を True にしない。"""
    e = enforcer or pick_enforcer()
    # **作業場は走りごとに分ける。** 共有すると、同時に2つ走ったときに壊れる。
    # 終わりに root を丸ごと消す作りなので、片方の片付けが相手の work を持っていく。
    #
    # 2026-09-13、対照つきで実測（報告はピア daigo-6e、こちらで再現）:
    #     単独        11○ 0★（32秒）
    #     同時に2つ   1本目 ★黙り / 2本目 ★黙り ＋ ★量
    #   ・黙り … 相手の中断記録まで数えて「掃除が見つけられない（中断 2 件）」
    #   ・量  … 相手に work を消され「手前で何も書けず、測れなかった」
    #
    # **ここで ★ が出ると、壁が無いものとして本物の仕事が止まる。**
    # 衝突しただけで仕事が止まるのは、証明の趣旨と逆。
    #
    # 鍵で直列にはしない。待ちや見送りが生まれると、それを ○ とも ★ とも書けず
    # 「測っていない」という第3の状態が要る。読み手（契約・受領証・掃除）が全員増えるので、
    # 機械全体を見る壁（CPU・時間・残党）が実際に揺れた例が出るまでは分離だけにする。
    # workroot を明に渡された場合は、呼んだ側の指定を尊重してそのまま使う。
    if workroot:
        root = real(workroot)
    else:
        base = real(os.path.join(HOME, ".guardrun-verify"))
        os.makedirs(base, exist_ok=True)
        _掃除(base)
        root = real(tempfile.mkdtemp(prefix="run-", dir=base))
    os.makedirs(root, exist_ok=True)
    証明の鍵 = _鍵を取る(os.path.join(HOME, ".guardrun-verify"))
    tmproot = real(tempfile.mkdtemp(prefix="verify-", dir=root))
    work = os.path.join(root, "work")
    os.makedirs(work, exist_ok=True)
    # **証明の中で走らせるものは、本物の置き場を汚さない。**
    # 汚すと、掃除が「証明の残骸」を毎回中断として拾い続ける。
    記録根 = os.path.join(root, "記録")
    後始末 = []          # 証明が落ちても機械に残さないための組
    # **囮の秘密を1つ置く。**本物の秘密（~/.ssh など）が在ることに頼ると、
    # 真っさらな機械では「1件も測れなかった」で ★ になり、**壁が効いて
    # いるのかどうか永久に分からない**（2026-09-12、Linux の container で
    # 13件すべて「無い」になった）。自分で置けば、どの機械でも必ず測れる。
    囮 = os.path.join(HOME, ".guardrun-秘密の見本")
    try:
        with 開く(囮, "w") as f:
            f.write("これが壁の中から読めたら、秘密は守られていない。" * 4)
        囮を置けた = True
    except OSError:
        囮を置けた = False
    out = {}
    try:
        c = contract([work], net=["localhost:11434"],
                     secrets=SECRETS + ([囮] if 囮を置けた else []),
                     記録=記録根)

        # ── 執行が動くか ──（**全部の試験の土台。ここが最初。**）
        #
        # 2026-09-12、Linux（Docker の中）で走らせて分かった：bwrap が
        # `Creating new namespace failed: Operation not permitted` で
        # **1つも起動しなかったのに、通信と CPU は ○ になった。**
        # 「外に出られない」も「2秒で終わった」も、**何も走っていなければ
        # そのとおりに見える。**壁が全部を拒否するように壊れると合格に
        # 見える、というのはこの形で起きる。
        #
        # macOS だけで回していたときは、この穴は一度も見えなかった。
        # **2台目に移したことで見つかった穴**なので、移植は正しさの試験でもある。
        動いた, 動出 = _probe(e, 小仕事.声(), c, work, tmproot)
        if 動いた != 0 or "ok" not in (動出 or ""):
            理由 = ("執行が1つも走らない: %s"
                    % " ".join((動出 or "（出力なし）").split())[:200])
            for w in ALL_WALLS:
                out[w] = (False, 理由)
            return out

        # ── 場所 ──
        中 = _probe(e, 小仕事.書く("inside.txt"), c, work, tmproot)
        外先 = os.path.join(root, "escaped.txt")
        if os.path.exists(外先):
            os.unlink(外先)
        _probe(e, 小仕事.書く(外先, "ng"), c, work, tmproot)
        抜けた = os.path.exists(外先)
        if 抜けた:
            os.unlink(外先)
        書けた = os.path.exists(os.path.join(work, "inside.txt"))
        # **誰でも書ける場所も試す。**家の中しか見ないと、uid を分けただけの
        # 執行（別ユーザ）を「場所も守れている」と読んでしまう。家は 750 なので
        # 別 uid は入れないが、/tmp には書けるからである。
        # 2つ目の執行を足して初めて見えた穴なので、試験の側に残す。
        誰でも = 小仕事.誰でも書ける所()
        的 = os.path.join(誰でも, "ng.txt")
        _probe(e, 小仕事.書く(的, "ng"), c, work, tmproot)
        誰でもに書けた = os.path.exists(的)
        shutil.rmtree(誰でも, ignore_errors=True)
        out[場所] = (書けた and not 抜けた and not 誰でもに書けた,
                     "中に書けない（執行が厳しすぎる）" if not 書けた
                     else "作業場の外に書けた" if 抜けた
                     else "誰でも書ける所（%s）に書けた" % os.path.dirname(的)
                     if 誰でもに書けた
                     else "中には書け、外にも誰でも書ける所にも書けない")

        # ── 秘密 ──
        # **1件ずつ確かめる。**まとめて1回では、効いていない1件が
        # 効いている9件に隠れる。しかも deny は書き方を外すと黙って
        # 無効になるので（firmlink の件）、書いたことは証拠にならない。
        #
        # **本番と同じ道（run() → 見届け役）で読む。**（2026-09-24・母艦）
        # 前は _probe で壁を直接呼んでいた。量・CPU と同じく、証明が本番の道を
        # 測っていないと、片方だけ直した日に証明が嘘をつく。
        #
        # **無い置き場所には偽物を置く。**（2026-09-24・母艦）
        # 真っさらな機械（GitHub の ubuntu）では 13件が「無い」で測れず、
        # 囮1件だけで ○ になっていた。偽物を置いて全部の置き場所を測る。
        # 置いた物は印で見分け、印の付いた物だけを消す（本物には触らない）。
        # 置くのは名指しの置き場所だけ（受領証の置き場や囮には置かない）
        置いた = _見本を置く([p for p in SECRETS + 家の中の見本
                             if p in c["読ませない"] or p in 家の中の見本])
        try:
            効いた, 駄目, 測れず = [], [], []
            for 番, 秘 in enumerate(list(c["読ませない"]) + 家の中の見本):
                外bytes = 0
                if os.path.isdir(秘):
                    for n in os.listdir(秘)[:50]:
                        try:
                            外bytes += os.path.getsize(os.path.join(秘, n))
                        except OSError:
                            pass
                elif os.path.isfile(秘):
                    try:
                        外bytes = os.path.getsize(秘)
                    except OSError:
                        外bytes = 0
                else:
                    測れず.append(os.path.basename(秘) + "（無い）")
                    continue
                if 外bytes == 0:
                    # 外でも読めないものは、塞げたのか元から空なのか区別できない
                    測れず.append(os.path.basename(秘) + "（外でも0バイト）")
                    continue
                読めた = _本番の道で読む(e, 秘, work, 記録根, "秘%d" % 番)
                if not 読めた.isdigit():
                    # 数が返らない＝試験が成立していない。**塞げた側に数えない。**
                    測れず.append(os.path.basename(秘) + "（数が返らない）")
                elif 読めた == "0":
                    効いた.append(秘)
                else:
                    駄目.append("%s が中から %s バイト読めた" % (秘, 読めた))
            # **通るべき側。**読みを許可制にしたので、対照は
            # 「作業場の中」と「家の外（/usr/bin/env）」の2つで見る。
            # 家の中の ~/.zshrc は、いまは読めないのが正しい。
            # 本番の道では作業場（run() に渡した場所）の中だけが読めるので、対照もその中に置く
            中場 = os.path.join(work, "読む", "中の対照")
            os.makedirs(中場, exist_ok=True)
            with 開く(os.path.join(中場, "readme.txt"), "w") as f:
                f.write("x" * 33)
            中身 = _本番の道で読む(e, os.path.join(中場, "readme.txt"), work, 記録根, "中の対照")
            外身 = _本番の道で読む(e, 小仕事.家の外の見本(), work, 記録根, "外の対照")
            ふつう読めた = (中身 not in ("0", "") and 外身 not in ("0", ""))
        finally:
            置き残し = _見本を片付ける(置いた)
        置いた数 = sum(1 for p, 種 in 置いた if 種 == "file")
        囮を測れた = 囮を置けた and 囮 in 効いた
        if 駄目:
            out[秘密] = (False, "／".join(駄目))
        elif 置き残し:
            out[秘密] = (False, "偽物を片付けられなかった: " + "・".join(置き残し))
        elif not 囮を測れた:
            # 本物が1件も無い機械でも、囮だけは必ず測れるはず。
            # 測れないなら試験が成立していないので、合格にしない。
            out[秘密] = (False, "囮の秘密すら測れていない（試験が成立していない）")
        elif not ふつう読めた:
            out[秘密] = (False, "作業場の中か /usr のものまで読めない（執行が厳しすぎる）")
        elif not 効いた:
            out[秘密] = (False, "1件も測れなかった（%s）" % "・".join(測れず))
        else:
            tail = "・測れず %d件" % len(測れず) if 測れず else ""
            偽 = "（うち偽物 %d件）" % 置いた数 if 置いた数 else ""
            out[秘密] = (True, "%d件すべて中から読めない%s%s" % (len(効いた), 偽, tail))

        # ── 通信 ──
        #
        # **執行によって、できる細かさが違う。**測り方も分ける。
        #   名指し（macOS/sandbox-exec） ollama にだけ出られること
        #   全遮断（Linux/bwrap）        どこにも出られないこと＋
        #                                名指しの契約が「拒否」されること
        # 同じ物差しを当てると、できないほうを「壊れている」と読むか、
        # できるほうを甘く見るかのどちらかになる。
        def 叩く(url, 契約, 外で=False):
            if not CURL:
                return None
            引数 = [CURL, "-s", "-m", "5", "-o", "/dev/null",
                    "-w", "%{http_code}", url]
            if 外で:
                try:
                    o = subprocess.run(引数, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                       timeout=20)
                    return (o.stdout or "").strip()
                except Exception:
                    return None
            return (_probe(e, 引数, 契約, work, tmproot)[1] or "").strip()

        def 届く(応答):
            """**HTTP の応答が1つでも返ったら、そこまで届いている。**（2026-09-24・Codex の監査）
            前は 200 だけを「出られた」と読み、プロキシの 403/407 やリダイレクトの 302 を
            「遮断できた」と数えていた（偽の curl で 403 を返させると ○ になった）。000 だけが届いていない印。"""
            return bool(応答) and 応答.isdigit() and 応答 != "000"

        if 通信 not in e.縛れる壁:
            # **原因を取り違えない。**囲っていない執行で「頭脳が止まっていて
            # 測れなかった」と出すと、ollama を起こせば直ると読めてしまう。
            out[通信] = (False, "この執行は通信を縛れない（%s）" % e.name)
        elif not CURL:
            out[通信] = (False, "curl が無いので通信を測れない"
                                "（測れないものを「効いている」と書かない）")
        elif e.通信の粒度 == "loopbackだけ":
            # **Windows。**外向きは SID を書いた規則で止まるが、
            # loopback は firewall の外側（WFP が触らない）なので必ず通る。
            # 「止まっている」と言えるのは外向きだけ。**言える範囲だけ言う。**
            c通 = contract([work], net=(), 記録=記録根)
            外で出られる = 届く(叩く("https://example.com", c通, 外で=True))
            中から外 = 叩く("https://example.com", c通)
            # **通るべき側②**：loopback の契約は受け、外向きの契約は断ること。
            近く, _ = e.契約を守れるか(
                contract([work], net=["localhost:11434"], 記録=記録根))
            遠く, _ = e.契約を守れるか(
                contract([work], net=["example.com:443"], 記録=記録根))
            out[通信] = (not 届く(中から外) and 外で出られる and 近く and not 遠く,
                         "外でも出られないので、塞げたのか元から無いのか分からない"
                         if not 外で出られる
                         else "壁の中から外に出られた（%s）" % 中から外
                         if 届く(中から外)
                         else "loopback の契約まで断ってしまう" if not 近く
                         else "外向きを名指しした契約を黙って受けてしまう" if 遠く
                         else "外へは出られない（loopback は firewall の外側なので"
                              "止められない。そう申告している）")
        elif e.通信の粒度 == "全遮断":
            c通 = contract([work], net=(), 記録=記録根)
            外で出られる = 届く(叩く("https://example.com", c通, 外で=True))
            中から外 = 叩く("https://example.com", c通)
            中からlocal = 叩く("http://127.0.0.1:11434/api/tags", c通)
            塞がった = not 届く(中から外) and not 届く(中からlocal)
            # **通るべき側①**：外では出られること。出られない機械で
            # 「塞げた」と言うのは、電源の切れた鍵を掛かっていると言うのと同じ。
            # **通るべき側②**：名指しの契約は拒否されること。
            # 守れない約束を黙って捨てる執行は、契約そのものを嘘にする。
            守れる, _なぜ = e.契約を守れるか(
                contract([work], net=["localhost:11434"], 記録=記録根))
            out[通信] = (塞がった and 外で出られる and not 守れる,
                         "外でも出られないので、塞げたのか元から無いのか分からない"
                         if not 外で出られる
                         else "壁の中から外に出られた（%s）" % 中から外
                         if 届く(中から外)
                         else "壁の中から localhost に出られた" if 届く(中からlocal)
                         else "行き先を名指しした契約を黙って受けてしまう"
                         if 守れる
                         else "どこにも出られない（この執行は名指しができないので、"
                              "行き先を書いた契約は拒否する）")
        else:
            try:
                import urllib.request
                urllib.request.urlopen("http://127.0.0.1:11434/api/tags",
                                       timeout=5).read(1)
                ollama = True
            except Exception:
                ollama = False
            外出 = 叩く("https://example.com", c)
            出られた = 届く(外出)
            # **通るべき側：外では出られること。**（2026-09-24）出られない機械で
            # 「外へは出られない」と言うのは、電源の切れた鍵を掛かっていると言うのと同じ。
            外で出られる = 届く(叩く("https://example.com", c, 外で=True))
            if not ollama:
                out[通信] = (False, "頭脳が止まっていて、通るべき側を測れなかった")
            elif not 外で出られる and not 出られた:
                out[通信] = (False, "外でも出られないので、塞げたのか元から無いのか分からない")
            else:
                届いた = 叩く("http://127.0.0.1:11434/api/tags", c) == "200"
                # **通るべき側③：外を名指しした契約なら、外まで届くこと。**（2026-09-25・未踏⑥）
                # 名前を引く道が塞がっていると、名指ししても1歩も出られない（Codex・Claude Code が動かない）。
                # 「出られない」は壁が効いている顔と同じなので、名指しした側で必ず確かめる。
                名指しで届く = 届く(叩く("https://example.com",
                                     contract([work], net=["*:443"], 記録=記録根)))
                out[通信] = (届いた and not 出られた and 名指しで届く,
                             "外のインターネットに出られた" if 出られた
                             else "ollama に届かない（仕事ができない）" if not 届いた
                             else "外を名指ししても届かない（名前を引く道が塞がっている）" if not 名指しで届く
                             else "ollama には届き、外へは出られない・外を名指しした契約なら届く")

        # ── 量 ──（rlimit。執行に依らない）
        # **本番と同じ道（run() → 見届け役）で測る。**（2026-09-24・母艦の指示）
        # 前は _probe で壁を直接呼んでいた。上限は見届け役が掛け直すので、
        # 特権なし Linux（sudo が rlimit を戻す）では本番は効いているのに証明だけ ★ だった。
        # 上限の掛け直しを _probe に書き写すと、次に片方だけ直した日に証明が嘘をつく。
        量場 = os.path.join(work, "量"); os.makedirs(量場, exist_ok=True)
        run([PY, "-c", "open('big','w').write('x'*5000000)"], 量場,
            max_file_bytes=65536, wall_sec=20, enforcer=e, prove=False, 記録=記録根)
        big = os.path.join(量場, "big")
        sz = os.path.getsize(big) if os.path.exists(big) else 0
        out[量] = (0 < sz <= 65536,
                   "上限を超えて %d バイト書けた" % sz if sz > 65536
                   else "手前で何も書けず、測れなかった" if sz == 0
                   else "5MB 書こうとして %d バイトで切れた" % sz)

        if os.name == "nt":
            out[量] = (False, "Windows には1ファイルの大きさの上限が無い（Job Object にも無い）")

        # ── 総量 ──
        # **止められる増えかたと、止められない増えかたがある。**
        # 5,000ファイルは 0.2 秒で書ける（実測）ので、1秒ごとの見回りは
        # 間に合わない。だから2つとも測る：
        #   長く続く増えかた … 見回りが止めること
        #   速い一気書き     … 止まらなくても、必ず赤と分かること
        # 片方だけ測ると、「量」の壁のときと同じ間違い（名前が防げる範囲より
        # 広く聞こえる）を繰り返す。
        続く = os.path.join(work, "続く"); os.makedirs(続く, exist_ok=True)
        r続 = run(小仕事.続けて増やす(),
                 続く, max_add_files=30, wall_sec=20, enforcer=e, prove=False, 記録=記録根)
        一気 = os.path.join(work, "一気"); os.makedirs(一気, exist_ok=True)
        r一 = run(小仕事.まとめて増やす(3000),
                 一気, max_add_files=50, enforcer=e, prove=False, 記録=記録根)
        素直 = os.path.join(work, "素直"); os.makedirs(素直, exist_ok=True)
        r素 = run(小仕事.まとめて増やす(5, "g"),
                 素直, max_add_files=50, enforcer=e, prove=False, 記録=記録根)
        # **宣言の仕組みそのものも測る。**
        # 宣言が効かなくなると npm install が壊れ、宣言が効きすぎると
        # 大量増加が素通しになる。どちらも黙って起きるので両方見る。
        宣言 = os.path.join(work, "宣言"); os.makedirs(宣言, exist_ok=True)
        r宣 = run(小仕事.まとめて増やす(1200),
                 宣言, 増える見込み="依存を入れる", enforcer=e, prove=False, 記録=記録根)
        打ち間違い = os.path.join(work, "誤"); os.makedirs(打ち間違い, exist_ok=True)
        r誤 = run(小仕事.書く("a.txt", "x"), 打ち間違い,
                 増える見込み="いっぱい", enforcer=e, prove=False, 記録=記録根)

        止めた = bool(r続["壁に当たった"])
        見つけた = r一["判定"] == "赤"
        通した = r素["判定"] == "緑" and not r素["壁に当たった"]
        宣言が効く = r宣["判定"] == "緑"
        誤りを弾く = r誤["判定"] == "拒否"
        out[総量] = (止めた and 見つけた and 通した and 宣言が効く and 誤りを弾く,
                     "続く増えかたを止められない" if not 止めた
                     else "速い一気書きを見つけられない" if not 見つけた
                     else "上限内まで止めてしまう（厳しすぎる）" if not 通した
                     else "宣言しても大量増加が通らない（npm install が壊れる）"
                     if not 宣言が効く
                     else "知らない宣言を黙って既定に落としている" if not 誤りを弾く
                     else "続く増えかたは止め、一気書きは赤、"
                          "宣言した増加は通す")

        # ── 仕掛け ──（あとで壁の外で走るものを見つけられるか）
        # 壁ではなく採点だが、**採点も黙って壊れる。**
        # 実際に .git を丸ごと除外していて、hooks を青と答えていた。
        def 仕掛け試験(名, 作る, 命令, 見込み="ふつう"):
            w = os.path.join(work, "仕" + 名)
            os.makedirs(w, exist_ok=True)
            作る(w)
            rr = run(命令, w, 増える見込み=見込み,
                     enforcer=e, prove=False, 記録=記録根)
            return rr["判定"]

        def npm下地(w):
            with 開く(os.path.join(w, "package.json"), "w") as f:
                json.dump({"name": "x", "scripts": {"test": "node t.js"}}, f)
            os.makedirs(os.path.join(w, "node_modules", ".bin"), exist_ok=True)

        def 足す(名):
            return [PY, "-c", "import json;p='package.json';"
                    "d=json.load(open(p));d['scripts'][%r]='echo';"
                    "json.dump(d,open(p,'w'))" % 名]
        赤1 = 仕掛け試験("a", npm下地, 足す("postinstall"))
        赤2 = 仕掛け試験("b", npm下地,
                       小仕事.走る道具を置く("node_modules/.bin/x"))
        静 = 仕掛け試験("c", npm下地,
                      小仕事.走る道具を置く("node_modules/.bin/x"),
                      見込み="依存を入れる")
        緑 = 仕掛け試験("d", npm下地, 足す("build"))
        赤3 = 仕掛け試験("e", lambda w: os.makedirs(
            os.path.join(w, ".git", "hooks"), exist_ok=True),
            小仕事.走る道具を置く(".git/hooks/pre-commit"))
        悪い = []
        if 赤1 != "赤":
            悪い.append("postinstall を見つけられない")
        if 赤3 != "赤":
            悪い.append(".git/hooks を見つけられない")
        if 赤2 != "赤":
            悪い.append("node_modules/.bin を見つけられない")
        if 静 == "赤":
            悪い.append("依存を入れる走りの .bin まで赤にする（騒ぎすぎ）")
        if 緑 != "緑":
            悪い.append("ふつうの scripts 追加まで赤にする（騒ぎすぎ）")
        out[仕掛け] = (not 悪い, "／".join(悪い) if 悪い
                       else "postinstall・.bin・.git/hooks を見つけ、"
                            "正当な変更では騒がない")

        # ── CPU ──
        # 量と同じく、本番と同じ道（run() → 見届け役）で測る（2026-09-24）。
        回場 = os.path.join(work, "回る"); os.makedirs(回場, exist_ok=True)
        t0 = time.time()
        CPU試験 = run([PY, "-c", "\nwhile True: pass"], 回場,
            cpu_sec=2, wall_sec=20, enforcer=e, prove=False, 記録=記録根)
        経過 = time.time() - t0
        # **手前で走らなかったものを「上限が効いた」と読まない。**
        # 何も起動しなければ 0 秒で帰ってくるので、速さは証拠にならない。
        走った = 経過 >= 1.0
        # Job 設定失敗まで速さだけで合格にしない。実際の上限判定も要る（2026-09-24）。
        CPUで止まった = CPU試験.get("壁に当たった") == "CPU時間の上限（2秒）"
        out[CPU] = (走った and 経過 < 15 and CPUで止まった,
                    "%.0f 秒回り続けた（上限が効かない）" % 経過 if 経過 >= 15
                    else "%.1f 秒で帰ってきた（そもそも走っていない疑い）" % 経過
                    if not 走った
                    else "CPU 上限で止まった証拠が無い" if not CPUで止まった
                    else "CPU 2秒の上限で %.0f 秒で止まった" % 経過)

        # ── 時間 ──（壁時計と孫の始末。run() の仕組みそのものを試す）
        # ── 時間 ──（ふつうの孫まで始末できるか）
        # 合否は pgrep のパターンに頼らない。**孫自身に印を書かせて、
        # それが現れるかを見る。**
        # 最初は pgrep -f "time.sleep(90)" で数えて、括弧が正規表現の
        # グループとして解釈され本文に当たっておらず、0件を「始末できた」と
        # 読んだ。実際は生き残っていた。**読めなかったことも証拠にしない。**
        def 逃げさせる(setsid, 片付ける=False):
            印 = os.path.join(work, "生きていた.txt")
            if os.path.exists(印):
                os.unlink(印)
            r = run(小仕事.孫を残す(印, 組を抜ける=setsid), work,
                    wall_sec=2, enforcer=e,
                    prove=False, 記録=記録根, 居座りも始末=片付ける)
            time.sleep(5)
            return bool(r["壁に当たった"]), os.path.exists(印)

        止まった, 生きた = 逃げさせる(setsid=False)
        out[時間] = (止まった and not 生きた,
                     "時間切れにならない" if not 止まった
                     else "殺したあとに孫が動いて印を書いた" if 生きた
                     else "2秒で止まり、ふつうの孫も動かなかった")

        # ── 残党 ──（自分でグループを作って親が即死する孫）
        # killpg は届かず、親が即死するので子孫としても辿れない。
        # **この執行では塞げない。**塞ぐには専用ユーザ（kill -u）が要る。
        # 既定の要求から外してあるが、**外したことを黙らない**ために測る。
        止まった2, 生きた2 = 逃げさせる(setsid=True)
        # **★ のままでよい。**掃除が作業場を掴んだ居座りを始末するように
        # なったが、それは「あとから見つかったものは残さない」であって
        # 「何も生き残らない」ではない（chdir されれば外れる）。
        # 壁と後始末を同じ名前で呼ぶと、防げる範囲より広く聞こえる。
        out[残党] = (止まった2 and not 生きた2,
                     "時間切れにならない" if not 止まった2
                     else "自分でグループを作った孫が、殺したあとも動いて印を書いた"
                          "（走りの最中は塞げない。あとで掃除が作業場を"
                          "掴んだものだけ始末する）"
                     if 生きた2 else "自分でグループを作った孫も動かなかった")

        # ── 記録 ──（採点表に、採点される側の手が届かないか）
        #
        # **ここが破れると、ほかの壁は全部意味を失う。**中から受領証を
        # 書き換えられるなら、何をしても「緑」と書いた紙を置いて出られる。
        # 壁は「悪いことをさせない」ためのものだが、記録は
        # 「**やったことが消えない**」ためのものなので、順番はこちらが先。
        os.makedirs(os.path.join(記録根, "runs"), exist_ok=True)
        的 = os.path.join(記録根, "runs", "のぞき.json")
        _確定書き(的, {"合言葉": "これが中から読めたら記録は守られていない"})
        書き先 = os.path.join(記録根, "runs", "なりすまし.json")
        # **本番と同じ道（run() → 見届け役）で測り、命令が本当に走ったかを対照で確かめる。**（2026-09-24）
        # 前は _probe で壁を直接呼び、終了コードも出力の形も見ていなかった。記録の試験のときだけ
        # 壁が立たないと「読めない・書けない」がそろって ○ になった（偽の壁で再現・Codex の監査 C8）。
        記場 = os.path.join(work, "記録"); os.makedirs(記場, exist_ok=True)
        対照 = os.path.join(記場, "記録の対照.txt")
        r記 = run([PY, "-c",
                  "open(%r,'w').write('x')\n"
                  "try:\n n=len(open(%r,'rb').read())\nexcept Exception:\n n=0\n"
                  "print('読めた', n)\n"
                  "try:\n open(%r,'w').write('x')\nexcept Exception:\n pass\n"
                  % (対照, 的, 書き先)],
                 記場, wall_sec=30, enforcer=e, prove=False, 記録=記録根)
        m = re.search(r"読めた (\d+)", r記.get("_出力") or "")
        走った = os.path.exists(対照)
        読めた数 = int(m.group(1)) if m else 0
        中から読めた = bool(読めた数)
        中から書けた = os.path.exists(書き先)
        # **通るべき側。**外からは読める（置き場そのものが壊れていない）。
        # これが無いと、置き場ごと消えている日を「守られている」と読む。
        外から読めた = _読む(的) is not None
        悪い = []
        if not 走った:
            悪い.append("試験の命令が走らなかった（測れず・判定=%s）" % r記.get("判定"))
        if 中から読めた:
            悪い.append("壁の中から受領証の置き場が読めた（%d バイト）" % 読めた数)
        if 中から書けた:
            悪い.append("壁の中から受領証の置き場に書けた（受領証を偽造できる）")
        if not 外から読めた:
            悪い.append("外からも読めない（置き場が壊れている）")
        out[記録] = (not 悪い, "／".join(悪い) if 悪い
                     else "置き場は中から読めも書けもせず、外からは読める")

        # ── 黙り ──（黙って終わった走りを、外側が必ず見つけるか）
        #
        # **実物で殺して確かめる。**親を SIGKILL するのは、電源断・OOM・
        # launchd の kill と同じ形で、この家がいちばん多く踏んだ壊れ方である。
        # 2026-09-12 の実測では、この形で
        #   仕事は起きた（a.txt が残る）／受領証は無い／子孫は生き残る
        # となり、**誰も何も知らないまま正常に見えた。**
        黙根 = os.path.join(root, "黙記録")
        子env = dict(os.environ)
        子env[RECORDS_ENV] = 黙根
        w黙 = os.path.join(work, "黙"); os.makedirs(w黙, exist_ok=True)
        殺す子 = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--証明なし", w黙,
             # **組を抜ける孫を混ぜる。**killpg では届かないので、
             # 作業場で探す網が効いているかまで、ここで見える。
             ] + 小仕事.書いて孫を残す(組を抜ける=True),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, env=子env)
        走り = None
        限 = time.time() + 20
        while time.time() < 限:
            for _d, 約, 受 in 記録を読む(黙根):
                if 約.get("状態") == "走行中" and not 受:
                    走り = 約
                    break
            if 走り:
                break
            time.sleep(0.2)
        try:
            殺す子.kill()
            殺す子.wait(timeout=10)
        except Exception:
            pass
        if 走り and 走り.get("子pgid"):
            後始末.append(走り["子pgid"])
        # **対照：親を殺したあと、本当に生き残りが居るのか。**
        # 居ないなら、掃除が「1本も見つけない」のは正しい。
        # Linux（bwrap の --die-with-parent）では親と一緒に片付くので、
        # 探す口が塞がっているのか、探す相手が居ないのかを、
        # ここで先に分けておく。分けずに「殺した数>0」を求めると、
        # **よく片付く機械ほど不合格になる。**
        time.sleep(0.5)
        実際に残った = []
        if 走り:
            実際に残った, _ = _組の生き残り(走り.get("子pgid"),
                                            走り.get("始めた") or time.time())
        悪い = []
        if not 走り:
            悪い.append("予告が現れない（走り出す前の約束が書かれていない）")
        else:
            s = sweep(黙根, kill=True)
            中断 = s["中断"]
            # **殺した走りの一時置き場まで片付いたか。**（2026-09-24）
            # 片付かないと、証明を取るたびに /private/tmp に1個ずつ残る。
            殺した置き場 = 走り.get("一時置き場")
            for _d, 約2, _受 in 記録を読む(黙根):
                殺した置き場 = 殺した置き場 or 約2.get("一時置き場")
            if not 殺した置き場:
                悪い.append("殺した走りの予告に一時置き場が書かれていない")
            elif os.path.lexists(殺した置き場):
                悪い.append("殺した走りの一時置き場が残った（%s）" % 殺した置き場)
            if len(中断) != 1:
                悪い.append("殺した走りを掃除が見つけられない（中断 %d 件）" % len(中断))
            else:
                x = 中断[0]
                証 = _読む(x.get("受領証") or "")
                足された = [a["path"] for a in (証 or {}).get(
                    "差分", {}).get("追加", [])]
                if not 証:
                    悪い.append("中断の受領証がディスクに残っていない")
                elif "a.txt" not in 足された:
                    悪い.append("受領証に、親が死ぬ前に書いたものが出ていない（%s）"
                                % 足された[:3])
                if x.get("残党", {}).get("生き残った"):
                    悪い.append("壁の中の残党を始末できていない（pid %s）"
                                % x["残党"]["生き残った"])
                elif 実際に残った and not x.get("残党", {}).get("殺した"):
                    悪い.append("生き残りが %d 本居たのに、掃除が1本も"
                                "見つけていない（見つける口が塞がっている）"
                                % len(実際に残った))

        # **通るべき側①：ふつうに終わった走りを、掃除が中断にしないこと。**
        # ここが無いと「全部を中断と呼ぶ掃除」でも上の試験は通る。
        w無 = os.path.join(work, "黙無"); os.makedirs(w無, exist_ok=True)
        try:
            subprocess.run([sys.executable, os.path.abspath(__file__),
                            "--証明なし", w無] + 小仕事.書く("b.txt", "x"),
                           capture_output=True, timeout=120, env=子env,
                           stdin=subprocess.DEVNULL)
        except Exception as ex:
            悪い.append("ふつうの走りが走らない（%s）" % ex)
        s2 = sweep(黙根, kill=False)
        if s2["中断"]:
            悪い.append("ふつうに終わった走りまで中断にした（%d 件）" % len(s2["中断"]))
        終わり = [r for _d, _y, r in 記録を読む(黙根) if r and r.get("作業場") == real(w無)]
        if not 終わり:
            悪い.append("ふつうに終わった走りの受領証が残っていない")
        elif 終わり[0].get("判定") != "緑":
            悪い.append("ふつうに終わった走りの判定が %s（緑のはず）" % 終わり[0].get("判定"))

        # **通るべき側②：生死の判定そのものに対照を置く。**
        # 判定を1つ足すたびに、その判定自身の対照を先に置く（2026-09-12 の教訓）。
        # pid 1 は必ず居るので、同じ pid で「本物」と「番号の使い回し」を作り分ける。
        # 生きている親は**自分**を使う。ここは持ち主まで揃っていないと
        # 対照にならない（pid 1 は root のものなので、signal が通らない
        # ＝「番号の使い回し」と同じ答えになる。最初これを対照に使って、
        # 自分の書いた判定を誤爆と読み違えた）。
        自分の経過 = _経過秒(os.getpid())

        def 偽記録(名, **上書き):
            r = {"id": 名, "状態": "走行中", "作業場": w無,
                 "命令": ["/bin/true"], "執行": e.name,
                 "始めた": time.time(), "期限": time.time() + 3600,
                 "親pid": os.getpid(),
                 "親の始まり": time.time() - (自分の経過 or 0),
                 "子pid": None, "子pgid": None, "機械の起動": _機械の起動()}
            r.update(上書き)
            d = os.path.join(黙根, "runs", 名)
            _確定書き(os.path.join(d, "予告.json"), r)
            _確定書き(os.path.join(d, "before.json"), {})
            return 名
        if 自分の経過 is None:
            悪い.append("自分の起動時刻が測れない（生死の判定に土台が無い）")
        生きてる = 偽記録("対照-生きている")                     # 自分＝確実に生存
        使い回し = 偽記録("対照-番号の使い回し",
                          始めた=time.time() - 86400, 親の始まり=time.time() - 86400)
        # **pid 1 を決め打ちしない。**（2026-09-24）普通のユーザで動くコンテナでは pid 1 が
        # 自分の sh になり、対照が成り立たず偽の ★ になった（crosstest ④ で実測）。
        # 判定（_親の生死）と同じ見分け方＝signal が通らない生きている pid を実際に探す。
        他人pid = _別の持ち主のpid(いまの機械().プロセス表())
        別人 = 偽記録("対照-別の持ち主", 親pid=他人pid) if 他人pid else None
        # 自分が root だと pid 1 にも signal が通るので、この対照は成立しない
        # （持ち主で見分ける道が無い）。**成立しない試験を合格にも不合格にもしない。**
        根で走っている = (_根か())
        再起動 = 偽記録("対照-機械が再起動", 機械の起動=1)
        # **親がゾンビの対照。**待ってもらえない親の下では、死んだ走りが
        # ずっと「走行中」に見える。ここを見ていないと、掃除は毎回
        # 0件を返しながら黙りを取りこぼす（Linux で実際にそうなった）。
        # わざと拾わない子を作る（wait() を呼ばない限りゾンビのまま残る）。
        ゾンビ = subprocess.Popen(小仕事.即終わる())
        time.sleep(0.4)
        親がゾンビ = 偽記録("対照-親がゾンビ", 親pid=ゾンビ.pid)
        s3 = sweep(黙根, kill=False)
        拾った = {x["id"] for x in s3["中断"]}
        if 生きてる in 拾った:
            悪い.append("生きている親の走りを中断にした（誤爆＝生きた仕事を殺す側）")
        if 使い回し not in 拾った:
            悪い.append("pid の使い回しを見分けられない（別人を生存と読む）")
        if 別人 and 別人 not in 拾った and not 根で走っている:
            悪い.append("別の持ち主の pid を自分の親と読んでいる")
        if 再起動 not in 拾った:
            悪い.append("機械の再起動を見分けられない")
        if 親がゾンビ not in 拾った:
            悪い.append("ゾンビの親を「生きている」と読んでいる"
                        "（死んだ走りが永久に走行中に見える）")
        try:
            ゾンビ.wait(timeout=5)      # ここで拾う（機械にゾンビを残さない）
        except Exception:
            pass
        # **通るべき側③：ふつうに終わった走りが、組を抜けた孫を置き去りにしない。**
        # 記録が閉じた走りは掃除が二度と見にこないので、ここが抜けると
        # 「毎回ひとりずつ置き去りにするが、誰にも分からない」形になる。
        #
        # **見るのは「走り終わったあとも生きているか」。**印が書かれたか
        # ではない（それは 残党 の壁の担当で、こちらの網は 0.2 秒より速い
        # 孫には間に合わない。同じ試験に両方を持たせると、どちらが
        # 効いているのか読めなくなる）。だから長く眠る孫で見る。
        w置 = os.path.join(work, "置き去り"); os.makedirs(w置, exist_ok=True)
        始 = time.time()
        r置 = run(小仕事.居座る(), w置, wall_sec=2, enforcer=e,
                 prove=False, 記録=記録根)
        残 = (r置.get("居座り") or {})
        まだ生きて, _ = _居座り(real(w置), 始)
        if まだ生きて:
            for x in まだ生きて:          # 試験の後始末（判定とは別に必ず消す）
                try:
                    os.kill(x["pid"], _強く殺す())
                except OSError:
                    pass
            悪い.append("ふつうに終わった走りが、組を抜けた孫を置き去りにした")
        elif not 残.get("殺した") and not out.get(残党, (False,))[0]:
            # **壁が先に止めているなら、網が空振りするのが正しい。**
            # Linux（bwrap の --unshare-pid）では組を抜けた孫がそもそも
            # 生き残らないので、殺す相手が居ない。網が塞がっているのか
            # 壁が効いているのかは、**残党 の判定で見分ける**
            # （★＝壁は止めない → そのとき網が空振りなら本当に塞がっている）。
            悪い.append("組を抜けた孫を1本も見つけていない"
                        "（作業場で探す網が塞がっている疑い）")

        out[黙り] = (not 悪い, "／".join(悪い) if 悪い
                     else "殺された走りは中断として受領証になり、"
                          "組を抜けた孫まで始末された"
                          "（ふつうの走り・生きている親は触らない）"
                          # **試せなかった対照を黙らない。**
                          + ("・別の持ち主の対照は試せず（この機械に他人のプロセスが無い）"
                             if not 他人pid and not 根で走っている else ""))

        # ── 跡（書いたのに残っていない、を言い分けられるか）──
        #
        # **差分は始まりと終わりしか見ない。**書いてから消した回は正味ゼロなので、
        # 「何もしなかった」と一文字も違わない受領証になっていた（2026-09-23 まで）。
        # フォルダの更新時刻は消したあとも残るので、それで割る。
        # **通るべき側（何もしない回）を必ず一緒に見る**——全部「書いた」と言う
        # ように壊れたら、この見分けは無いのと同じなので。
        def _受(命令):
            w = os.path.join(work, "跡%d" % (abs(hash(命令[-1])) % 10000))
            os.makedirs(w, exist_ok=True)
            r = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--証明なし", w] + 命令,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=子env)
            try:
                t = r.stdout
                return json.loads(t[t.index("{"):])
            except (ValueError, KeyError):
                return {}
        悪い = []
        書消 = _受(小仕事.書いて消す())
        無為 = _受(小仕事.何もしない())
        if 書消.get("触った跡") is not True:
            悪い.append("書いてから消した回に跡が残らない（触った跡=%s）"
                        % 書消.get("触った跡"))
        elif "更新の跡はある" not in " ".join(書消.get("理由") or []):
            悪い.append("跡はあるのに、受領証が更新の跡を説明しない")
        if 無為.get("触った跡") is not False:
            悪い.append("何もしない回まで跡ありと言う（触った跡=%s）＝見分けになっていない"
                        % 無為.get("触った跡"))
        if 書消.get("判定") != "青" or 無為.get("判定") != "青":
            悪い.append("判定が青でなくなっている（書いて消す=%s／何もしない=%s）"
                        % (書消.get("判定"), 無為.get("判定")))
        out[跡] = (not 悪い, "／".join(悪い) if 悪い
                   else "書いてから消した回は「更新の跡はある」と言い、"
                        "何もしない回は跡なしと言った（どちらも青のまま）")
    finally:
        if 囮を置けた:
            try:
                os.unlink(囮)
            except OSError:
                pass
        # **証明が落ちても、機械に残さない。**残すと、次の証明が
        # 前の証明の残骸を数えて、原因の分からない失敗になる。
        for 組 in 後始末:
            try:
                _組ごと殺す(組, 組そのもの=True)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)
        try:
            証明の鍵.close()      # flock は閉じれば外れる
        except Exception:
            pass
    return out


# ── 受領証 ────────────────────────────────────────────────────

SKIP_DIRS = {"node_modules", "__pycache__", ".venv", "dist", "build",
             ".next", ".cache", ".DS_Store"}

# **.git は丸ごと外さない。**2026-09-11、ピアが実際にやって見せた：
# 壁の中から .git/hooks/pre-commit を書いて実行ビットまで付けられ、
# それでも差分は「何も変わっていない＝青」を返した。そのフックは、
# あとで誰かが**壁の外で** git commit した瞬間に走る。
# 中身（objects）は大きくて騒がしいので見ないが、**あとで外で走るもの**
# ——hooks と config——だけは必ず見る。
# `.git` の中で降りない場所（大きくて騒がしいだけのもの）。
# **「見る先」を数えるのをやめ、「降りない先」を数える形にした。**
# 2026-09-11、hooks だけを降りる形にしていたら
# `.git/modules/<名前>/hooks/pre-commit` を見落とした（ピアが実測）。
# サブモジュールは入れ子にできて名前も自由なので、
# 見る先を数え上げると必ず漏れる。
GIT_降りない = {"objects", "lfs", "refs", "logs", "rr-cache", "worktrees"}


def _git配下で見るか(rel):
    """`.git` の中のこのファイルを採点に入れるか。

    入れるのは **あとで壁の外で走るもの** だけ：
      どこかの hooks/ の下  … サブモジュールの入れ子も含む
      config                … core.hooksPath・filter・alias はここを通る
    """
    r = "/" + rel.replace(os.sep, "/")
    return "/hooks/" in r or r.endswith("/config")


def snapshot(root, max_files=20000):
    """いまの中身を記録する。パス → (バイト数, 非空行数, ハッシュ)。

    **行数まで採るのは差し引きで見るため。**モデルは書き足してから消す
    ことがあるので、「変更あり」だけでは足りない。"""
    out = {}
    root = real(root)

    def 読めない場所(ex):
        # **読めないフォルダを黙って飛ばさない。**（2026-09-24・Codex の監査）
        # 別 uid の命令が 0700 のフォルダに書くと、人の側の os.walk は黙って飛ばし、
        # 中身が差分にも総量にも入らず青になった（実走で確認）。
        rel = os.path.relpath(getattr(ex, "filename", None) or root, root)
        out[rel + os.sep] = (-1, -1, "読めない場所")
    for dirpath, dirnames, filenames in os.walk(root, onerror=読めない場所):
        rel_dir = os.path.relpath(dirpath, root)
        飾り = os.sep + rel_dir + os.sep
        git配下 = rel_dir == ".git" or (os.sep + ".git" + os.sep) in 飾り
        if git配下:
            dirnames[:] = [d for d in dirnames if d not in GIT_降りない]
            filenames = [f for f in filenames
                         if _git配下で見るか(os.path.join(rel_dir, f))]
        else:
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_DIRS:
                continue
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root)
            try:
                st = os.lstat(p)
                if stat.S_ISLNK(st.st_mode):
                    # **リンクを飛ばさない。**（2026-09-24）.git/hooks/pre-commit をリンクで置くと
                    # 差分に出ず、hooks の赤旗をすり抜けて緑になった（実走で確認）。指す先ごと記録する。
                    out[rel] = (0, 0, "リンク→" + os.readlink(p))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    # **FIFO などを開かない。**素直に open すると書き手が来るまで永久に待ち、
                    # 走りが終わっているのに受領証が出なかった（2026-09-24・実走で固まった）。
                    out[rel] = (0, 0, "特殊ファイル")
                    continue
                if st.st_size > 4_000_000:
                    continue
                fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        out[rel] = (0, 0, "特殊ファイル")
                        continue
                    with os.fdopen(fd, "rb") as f:
                        fd = None
                        b = f.read()
                finally:
                    if fd is not None:
                        os.close(fd)
            except OSError:
                # **読めなかったことを黙って飛ばさない。**uid を分けると、
                # agent は自分だけが読めるファイル（600）を作れる。飛ばすと
                # **受領証から消える**＝置いたのに置いていないことにできる。
                # 中身が読めないなら、読めないという事実を差分に残す。
                out[rel] = (-1, -1, "読めなかった")
                continue
            lines = sum(1 for ln in b.split(b"\n") if ln.strip())
            out[rel] = (len(b), lines, hashlib.sha256(b).hexdigest())
            if len(out) >= max_files:
                return out
    return out


def diff(before, after):
    """前と後を突き合わせる。**これが唯一の「やったこと」の証拠。**
    画面に出た文字は見ない。ここに出ない変更は、起きていない。"""
    added, removed, changed = [], [], []
    for k, v in after.items():
        if k not in before:
            added.append({"path": k, "行": v[1]})
        elif before[k][2] != v[2]:
            was, now = before[k][1], v[1]
            changed.append({
                "path": k, "前": was, "後": now, "差し引き": now - was,
                # 2026-09-10、442行から111行（25%）が消えた事故がここに当たる。
                "縮小率": round((was - now) / was, 3) if was and now < was else 0.0,
            })
    for k in before:
        if k not in after:
            removed.append({"path": k, "行": before[k][1]})
    return {"追加": added, "削除": removed, "変更": changed}


def verdict(d, shrink_limit=0.30, shrink_min_lines=10):
    """差分の危険信号を判定する。緑も、依頼の達成や内容の正しさの証明ではない。

    縮小率だけでは、不要な import を除く 3→2 行まで赤になる（未踏⑥ E2）。
    10行未満の縮小は注意に留める。ただし空になる変更・削除・仕掛けは赤のまま。
    10行は警告の運用基準であり、安全性を実証した境界ではない。
    """
    reasons = []
    notes = []
    for c in d["変更"]:
        if c["縮小率"] >= shrink_limit:
            reason = "%s が %d%% 縮んだ（%d行→%d行）" % (
                c["path"], round(c["縮小率"] * 100), c["前"], c["後"])
            if c["後"] <= 0 or c["前"] - c["後"] >= shrink_min_lines:
                reasons.append(reason)
            else:
                notes.append(reason + "。少量の縮小として注意（内容の正しさは未判定）")
    for r in d["削除"]:
        reasons.append("%s が消えた（%d行）" % (r["path"], r["行"]))
    # **あとで壁の外で走るものが置かれていないか。**
    # これは「壁の中に閉じ込めた」を後ろから破る仕掛けなので、
    # 縮んだかどうかとは別に、置かれただけで赤にする。
    for c in d["追加"] + d["変更"]:
        path = "/" + c["path"].replace(os.sep, "/")
        if "/.git/" in path and ("/hooks/" in path or path.endswith("/config")):
            reasons.append("%s が置かれた（あとで壁の外で走る）" % c["path"])
    if reasons:
        return "赤", reasons + notes
    if not (d["追加"] or d["変更"]):
        return "青", ["何も変わっていない"]
    return "緑", notes


# **壁の中の見届け役。**（2026-09-23）
# 壁が立ったか・命令がどう終わったかを、**出力の文字から推し量らない。**
# 文字で読んでいた頃は、Codex のレビューで5つのすり抜けが出た（関数に直に当てて確認）：
#   対話モードでは出力が端末に流れて判定に届かない（qwc が毎回これ）／
#   先に警告が1行出ると見逃す／sudo の段の失敗は名乗りが違う／
#   中身が `bwrap:` と言うと壁の失敗にされる／自分で exit 130 した命令をシグナル扱い。
# 見届け役は壁の**いちばん内側**で最初に動き、一時置き場（どの執行でも中から書ける）に
#   「起動」→ 子の本当の終わり方（waitpid の結果）
# を書く。外はこの記録だけで決める。**書かれていなければ、壁の中に届いていない。**
# 終了コードは変えない：子がシグナルで落ちたら、見届け役も同じシグナルで落ちる。
_見届け役の中身 = r"""import os, signal, stat, subprocess, sys
道 = sys.argv[1]
def 書く(s):
    # 普通のファイルにだけ・待たずに書く。中の命令は同じ権限なので、記録を
    # FIFO やリンクに差し替えられる（2026-09-23 実走で guardrun が固まった）。
    try:
        fd = os.open(道, os.O_WRONLY | os.O_APPEND | os.O_CREAT
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o644)
    except OSError:
        return
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            os.write(fd, (s + "\n").encode("utf-8"))
            os.fsync(fd)
    finally:
        os.close(fd)
書く("起動")
# 上限を、壁のいちばん内側で掛け直す（下げる向きだけ・バイト単位）。
# Linux の sudo は PAM で rlimit を unlimited に戻すので、外で掛けた分は消えている。
上限 = __上限__
try:
    import resource
    for 名, 値 in zip(("RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE"), 上限 or ()):
        if 値:
            r = getattr(resource, 名)
            _soft, hard = resource.getrlimit(r)
            新 = 値 if hard == resource.RLIM_INFINITY else min(値, hard)
            # CPU だけは hard を少し上に置く。Linux は soft=hard だと SIGXCPU を送らず
            # いきなり SIGKILL（137）で、上限に当たったのに「中断」と読まれていた（2026-09-24・④で実測）。
            硬 = 新
            if 名 == "RLIMIT_CPU":
                硬 = 新 + 2 if hard == resource.RLIM_INFINITY else min(新 + 2, hard)
            resource.setrlimit(r, (新, 硬))
except Exception:
    pass
# **Linux では、命令の側だけに Landlock を掛ける。**（2026-09-24・母艦・未踏③）
# 見届け役と命令は同じ権限なので、命令はこの記録を偽造・消去・差し替え・切り詰めでき、
# 見届け役を殺せた。外の突き合わせで後から見抜いていたのを、**カーネルがその場で断る**形にする。
#   書き込み系（書く・消す・作る・名前を変える・切り詰める）は 作業場・中/・/dev の下だけ
#   自分のドメインの外へのシグナルは禁止（ABI 6 から）
# 見届け役自身には掛けない。記録は 置き場/見届け.txt、命令の一時領域は 置き場/中/ に分ける
# （Landlock は許す場所を並べる形なので、同じフォルダの中で1ファイルだけ除けない）。
# 試作と測定: ~/未踏/実測/07（攻撃5種 なし 0/5 → あり 5/5 本物・掛ける手間 88.5µs）。
書ける = __書ける__
env = None
前置 = None
閉じ込め = "なし（Linux でない）"
if sys.platform.startswith("linux") and 書ける is not None:
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        版 = libc.syscall(444, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
        if 版 < 1:
            閉じ込め = "なし（この機械のカーネルに Landlock が無い）"
        else:
            置 = os.path.dirname(os.path.abspath(道))
            中 = os.path.join(置, "中")
            os.makedirs(中, exist_ok=True)
            # guardrun が前もって置いた物（.gitconfig の safe.directory など）を 中/ へ写す。
            # 付け替えた先に無いと、git の所有者の確かめで qwc が止まる。
            import shutil as _sh
            for _n in os.listdir(置):
                if _n in ("中", "見届け役.py", os.path.basename(道)):
                    continue
                _src = os.path.join(置, _n)
                if os.path.isfile(_src) and not os.path.islink(_src):
                    _sh.copy2(_src, os.path.join(中, _n))
            # 一時置き場を指す環境（TMPDIR・HOME・GIT_CONFIG_GLOBAL…）を 中/ へ付け替える
            env = {k: (中 + v[len(置):] if v == 置 or v.startswith(置 + "/") else v)
                   for k, v in os.environ.items()}
            扱う = sum(1 << i for i in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12))
            if 版 >= 2:
                扱う |= 1 << 13
            if 版 >= 3:
                扱う |= 1 << 14
            範囲 = (1 << 1 | 1 << 0) if 版 >= 6 else 0      # シグナル・抽象 unix ソケット
            許す先 = [(p, 扱う) for p in 書ける + [中] if os.path.isdir(p)] + [("/dev", 1 << 1)]

            class _Attr(ctypes.Structure):
                _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64), ("scoped", ctypes.c_uint64)]

            class _Rule(ctypes.Structure):
                _pack_ = 1
                _fields_ = [("allowed", ctypes.c_uint64), ("fd", ctypes.c_int32)]

            def 前置():
                a = _Attr(扱う, 0, 範囲)
                大 = 24 if 版 >= 6 else 16 if 版 >= 4 else 8
                fd = libc.syscall(444, ctypes.byref(a), ctypes.c_size_t(大), ctypes.c_uint32(0))
                if fd < 0:
                    os._exit(126)
                for p, 許 in 許す先:
                    pfd = os.open(p, os.O_PATH | os.O_CLOEXEC)
                    r = _Rule(許, pfd)
                    if libc.syscall(445, ctypes.c_int(fd), ctypes.c_int(1), ctypes.byref(r),
                                    ctypes.c_uint32(0)) < 0:
                        os._exit(126)
                    os.close(pfd)
                if libc.prctl(38, 1, 0, 0, 0) != 0 or \
                        libc.syscall(446, ctypes.c_int(fd), ctypes.c_uint32(0)) < 0:
                    os._exit(126)          # 掛けられないなら走らせない（黙って素で走らせない）
                os.close(fd)
            閉じ込め = "landlock ABI %d" % 版
    except Exception as e:                                  # noqa: BLE001
        env, 前置 = None, None
        閉じ込め = "なし（%s: %s）" % (type(e).__name__, e)

if sys.platform == "darwin" and 書ける is not None:
    import json as _json
    import shutil as _sh
    置 = os.path.dirname(os.path.realpath(道))
    中 = os.path.join(置, "中")
    os.makedirs(中, exist_ok=True)
    for _n in os.listdir(置):
        if _n in ("中", "見届け役.py", os.path.basename(道)):
            continue
        _src = os.path.join(置, _n)
        if os.path.isfile(_src) and not os.path.islink(_src):
            _sh.copy2(_src, os.path.join(中, _n))
    env = {k: (中 + v[len(置):] if v == 置 or v.startswith(置 + "/") else v)
           for k, v in os.environ.items()}
    # 子に既存の規則と記録保護を一度だけ掛ける。見届け役は uid 境界の内側、
    # Seatbelt の外側に置く（二重の sandbox_apply は macOS が拒否する）。
    _profile = __MAC_PROFILE__ + (
                '(deny file-write* (require-all (subpath %s) (require-not (subpath %s))))'
                '(deny signal (require-not (target same-sandbox)))') % (
                    _json.dumps(置, ensure_ascii=False), _json.dumps(中, ensure_ascii=False))
    sys.argv[2:] = ["/usr/bin/sandbox-exec", "-p", _profile] + sys.argv[2:]
    閉じ込め = "seatbelt child separation"

書く("閉じ込め " + 閉じ込め)
# **別利用者になった後で Job を作る。**（2026-09-24）
# Start-Process の外からではなく、実際に子を起こす見届け役が CPU を縛る。
# Job は子孫のユーザー CPU 時間の合計。1ファイルの大きさを縛る口は無い。
job = None
p = None
try:
    if sys.platform == "win32" and 上限 and 上限[0]:
        import ctypes as ct
        # Windows の DWORD は64ビット Python でも32ビット。HANDLE はポインタ幅。
        D, Q, S, H = ct.c_uint32, ct.c_int64, ct.c_size_t, ct.c_void_p
        class _基本(ct.Structure):
            _fields_ = [("PerProcessUserTimeLimit", Q), ("PerJobUserTimeLimit", Q),
                        ("LimitFlags", D), ("MinimumWorkingSetSize", S),
                        ("MaximumWorkingSetSize", S), ("ActiveProcessLimit", D),
                        ("Affinity", S), ("PriorityClass", D), ("SchedulingClass", D)]
        class _IO(ct.Structure):
            _fields_ = [(n, ct.c_uint64) for n in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class _拡張(ct.Structure):
            _fields_ = [("BasicLimitInformation", _基本), ("IoInfo", _IO),
                        ("ProcessMemoryLimit", S), ("JobMemoryLimit", S),
                        ("PeakProcessMemoryUsed", S), ("PeakJobMemoryUsed", S)]
        class _計時(ct.Structure):
            _fields_ = [("TotalUserTime", Q), ("TotalKernelTime", Q),
                        ("ThisPeriodTotalUserTime", Q), ("ThisPeriodTotalKernelTime", Q),
                        ("TotalPageFaultCount", D), ("TotalProcesses", D),
                        ("ActiveProcesses", D), ("TotalTerminatedProcesses", D)]
        k = ct.WinDLL("kernel32", use_last_error=True)
        for 名, 引数, 戻り in (
                ("CreateJobObjectW", [H, ct.c_wchar_p], H),
                ("SetInformationJobObject", [H, ct.c_int, H, D], ct.c_int),
                ("AssignProcessToJobObject", [H, H], ct.c_int),
                ("QueryInformationJobObject", [H, ct.c_int, H, D, H], ct.c_int),
                ("CloseHandle", [H], ct.c_int)):
            f = getattr(k, 名)
            f.argtypes, f.restype = 引数, 戻り
        def 確かめる(ok):
            if not ok:
                raise ct.WinError(ct.get_last_error())
        job = k.CreateJobObjectW(None, None)
        確かめる(job)
        info = _拡張()
        info.BasicLimitInformation.PerJobUserTimeLimit = int(上限[0] * 10000000)
        # JOB_TIME と KILL_ON_JOB_CLOSE。見届け役が失敗しても子孫を残さない。
        info.BasicLimitInformation.LimitFlags = 0x4 | 0x2000
        確かめる(k.SetInformationJobObject(job, 9, ct.byref(info), ct.sizeof(info)))
    p = subprocess.Popen(sys.argv[2:], env=env, preexec_fn=前置)
    if job:
        # 起動直後に割り当てる。割り当て前の短い間は未制限（2026-09-24）。
        # 割り当てに失敗した走りを、上限つきの成功に見せない。
        確かめる(k.AssignProcessToJobObject(job, int(p._handle)))
except OSError as e:
    if p is not None:
        p.kill()
        p.wait()
    if job:
        k.CloseHandle(job)
    書く("起こせない %s" % type(e).__name__)
    sys.exit(127)
# 対話で押された Ctrl-C は子が受ける。見届け役が先に死ぬと、終わり方を書けない。
# **無視せず子へ渡す。**（2026-09-24・M7）前は SIG_IGN で、Ctrl-C も Ctrl-Z も命令に届かなかった
# （pty で送って実測: 命令は受けず、Ctrl-Z でも20秒走り切った）。見届け役自身は落ちずに、子へ中継する。
def _渡す(n, _f):
    try:
        os.kill(p.pid, n)
    except OSError:
        pass
for s in ("SIGINT", "SIGQUIT", "SIGTSTP", "SIGCONT", "SIGTERM", "SIGHUP"):
    if hasattr(signal, s):
        signal.signal(getattr(signal, s), _渡す)
# 子の本当の終わり方と、**使った CPU 時間**を取る（上限に当たったのか、自分で
# SIGXCPU を送っただけかを見分けるため・2026-09-24）。
cpu = None
while True:
    try:
        if hasattr(os, "wait4"):
            _pid, st, ru = os.wait4(p.pid, 0)
            code = -os.WTERMSIG(st) if os.WIFSIGNALED(st) else os.WEXITSTATUS(st)
            p.returncode = code
            cpu = ru.ru_utime + ru.ru_stime
        else:
            code = p.wait()
        break
    except InterruptedError:
        continue
if job:
    try:
        used = _計時()
        確かめる(k.QueryInformationJobObject(job, 1, ct.byref(used), ct.sizeof(used), None))
        cpu = used.TotalUserTime / 10000000
        # Job 時間切れの既定値は ERROR_NOT_ENOUGH_QUOTA (1816)。値だけでは
        # 自分で同じ値を返した子と区別できないので、Job の計時も突き合わせる。
        # Windows に SIGXCPU は無い。記録は -24、外へは 152 として同じ照合に乗せる。
        if code == 1816 and used.TotalUserTime >= int(上限[0] * 10000000):
            code = -24
    except OSError:
        書く("CPU計時失敗")
    finally:
        k.CloseHandle(job)
書く("終了 %d%s" % (code, "" if cpu is None else " cpu %.2f" % cpu))
if code < 0 and os.name != "nt":
    # SIGKILL・SIGSTOP はハンドラを置けない（置こうとすると OSError で 1 に化けた）。
    try:
        signal.signal(-code, signal.SIG_DFL)
    except (OSError, ValueError):
        pass
    os.kill(os.getpid(), -code)
sys.exit(152 if job and code == -24 else code if code >= 0 else 1)
"""


def _開けたものの記録(e):
    """執行（重ねの中も）が開けた穴を、予告に書ける形で返す。"""
    出 = []
    for x in (e, getattr(e, "外", None), getattr(e, "内", None)):
        if x is not None and getattr(x, "_開けた", None):
            # Windows の執行は場所を文字列で持つ（list() にすると1文字ずつにばらける）
            出.append({"執行": type(x).__name__,
                       "開けた": [list(y) if isinstance(y, tuple) else y for y in x._開けた],
                       "元のgid": getattr(x, "_元のgid", None)})
    return 出


def _開けたものを外す(e, 記録, workdir, tmproot):
    """予告に書いた穴を、あとから外す（sweep 用）。**例外を投げない。**"""
    try:
        for 書 in 記録 or []:
            for x in (e, getattr(e, "外", None), getattr(e, "内", None)):
                if x is not None and type(x).__name__ == 書.get("執行") and hasattr(x, "片付け"):
                    x._開けた = [tuple(y) if isinstance(y, list) else y for y in 書.get("開けた") or []]
                    x._元のgid = 書.get("元のgid")
                    x.片付け(None, workdir, tmproot)
    except Exception:                                    # noqa: BLE001
        pass


def _片付けてよい一時置き場(道):
    """guardrun が作った形（既知の親の直下の guardrun-*）か。それ以外は消さない。"""
    try:
        r = real(道)
    except Exception:                                    # noqa: BLE001
        return False
    if not os.path.basename(r).startswith("guardrun-") or os.path.islink(道):
        return False
    親たち = {real(tempfile.gettempdir())}
    for x in ("/private/tmp", "/tmp"):
        if os.path.isdir(x):
            親たち.add(real(x))
    return os.path.dirname(r) in 親たち


def _一時置き場を消す(e, tmproot):
    """一時置き場を消して、**消せなかった物を返す。**（2026-09-24）

    `rmtree(ignore_errors=True)` は消し損ねを黙って捨てていた。
    別 uid の 0700 の中を覗けない・SIGKILL で片付けに届かない、の2つで
    /private/tmp/guardrun-* が約50個たまっていた（Codex の調査・実物で確認）。
    **ここでは直さず、残ったことを受領証に書く。**直すのは 本人の物を消す と sweep。"""
    残り = []

    def 記す(_fn, path, exc):
        ex = exc[1] if isinstance(exc, tuple) else exc
        残り.append("%s: %s" % (path, getattr(ex, "strerror", None) or type(ex).__name__))
    try:
        if e is not None:
            e.本人の物を消す(tmproot)
    except Exception:                                    # noqa: BLE001
        pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(tmproot, onexc=記す)
    else:
        shutil.rmtree(tmproot, onerror=記す)
    if os.path.lexists(tmproot) and not 残り:
        残り.append("%s: 消したのに残っている" % tmproot)
    return 残り[:10]


def _見届けを読む(道):
    """(起動した, 終わり方) を返す。終わり方は ("終了", n) / ("起こせない", 名) / None。
    起動した は True / False / "差し替え"（記録が普通のファイルでなくなっていた）。
    **決して例外を投げない**（片付けの直前で呼ぶので、ここで落ちると ACL が残る）。"""
    # **普通のファイルか確かめ、待たずに、量を限って読む。**
    # 中の命令が記録を FIFO に差し替えると、素直に open した外側が永久に待ち、
    # 片付け（ACL を外す）まで届かなかった（2026-09-23 実走）。
    try:
        fd = os.open(道, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return "差し替え", None      # 普通のファイルでない＝中から差し替えられた
            中身 = os.read(fd, 4096).decode("utf-8", "replace")
        finally:
            os.close(fd)
        行 = [x.strip() for x in 中身.splitlines() if x.strip()]
    except OSError as ex:
        # 無い（ENOENT）は「書かれていない」。リンクに差し替えられた（ELOOP）は差し替え。
        import errno
        return ("差し替え" if ex.errno == errno.ELOOP else False), None
    except Exception:                                    # noqa: BLE001
        return False, None
    終わり = None
    for x in 行:
        if x.startswith("終了 "):
            try:
                語 = x.split()
                終わり = ("終了", int(語[1]))
                if len(語) >= 4 and 語[2] == "cpu":
                    終わり = 終わり + (float(語[3]),)
            except (IndexError, ValueError):
                pass
        elif x.startswith("起こせない"):
            終わり = ("起こせない", x.split(" ", 1)[-1])
    # 「起動」の行を消されても、見届け役が終わりを書いたなら起動はしている。
    return ("起動" in 行 or 終わり is not None), 終わり


def _閉じ込めを読む(道):
    """見届け役が書いた「閉じ込め …」の行を返す。無ければ None。**例外を投げない。**
    （中から書ける記録なので参考。掛かっていない走りを掛かったと言い張ることはできても、
    掛かった走りで命令がこの行を書き換えることはカーネルが断る。）"""
    try:
        fd = os.open(道, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            中身 = os.read(fd, 4096).decode("utf-8", "replace")
        finally:
            os.close(fd)
    except Exception:                                    # noqa: BLE001
        return None
    for x in 中身.splitlines():
        if x.startswith("閉じ込め "):
            return x.split(" ", 1)[1].strip()
    return None


def _最大のファイル(root):
    """作業場でいちばん大きい普通のファイルのバイト数（中身は読まない・リンクは辿らない）。"""
    最大 = 0
    for dirpath, _dirs, files in os.walk(root):
        for n in files:
            try:
                st = os.lstat(os.path.join(dirpath, n))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_size > 最大:
                最大 = st.st_size
    return 最大


def _hitを決める(終わり, code, 量超え, killed, cpu_sec, max_file_bytes, 最大ファイル=None):
    # **自分で返した 128+signal を、壁が止めた証拠にしない。**（2026-09-23）
    # 終了の記録があれば本当のシグナルだけを採り、無いときだけ外のコードで補う。
    # **ただし記録は中の命令にも書ける。**外の終了コードと合うときだけ信じる。
    # 偽の「終了 -SIGXCPU」を書いて見届け役を殺すと、記録だけで上限に当たったことにされ、
    # 突き合わせまで飛ばして青になった（2026-09-24・Codex のレビュー）。
    記録あり = (終わり is not None and 終わり[0] == "終了"
              and _記録と終了コードが合うか(終わり, code))
    n = 終わり[1] if 記録あり else code
    # **自分でシグナルを送っただけの走りを「上限に当たった」にしない。**（2026-09-24・Codex の監査）
    # SIGXCPU なら実際に上限近くまで CPU を使ったか、SIGXFSZ なら上限の大きさまで書いたファイルがあるか。
    使った = 終わり[2] if 記録あり and len(終わり) > 2 else None
    if 量超え:
        return 量超え[0]
    # Windows の Job 時間切れは見届け役が -24／152 に揃える（2026-09-24）。
    # 生の 1816 は他の理由でも返せるので、CPU の証拠として採らない。
    if sys.platform == "win32" and 記録あり and n == -24 \
            and 使った is not None and 使った >= cpu_sec:
        return "CPU時間の上限（%d秒）" % cpu_sec
    if _XCPU and (n == -_XCPU if 記録あり else n in (-_XCPU, 128 + _XCPU)) \
            and (使った is None or 使った >= cpu_sec * 0.8):
        return "CPU時間の上限（%d秒）" % cpu_sec
    if _XFSZ and (n == -_XFSZ if 記録あり else n in (-_XFSZ, 128 + _XFSZ)) \
            and (最大ファイル is None or 最大ファイル >= max_file_bytes):
        return "1ファイルの大きさの上限（%d バイト）" % max_file_bytes
    return killed if killed else None


def _記録と終了コードが合うか(終わり, code):
    """見届けの記録と、外から見た本物の終了コードが合うか。

    **記録は中の命令にも書ける**（同じ権限）。偽の「終了 0」を書いて見届け役を殺すと、
    記録だけ見れば青になった（2026-09-23 実走・Codex の指摘）。だが見届け役を殺せば
    外の終了コードはシグナルになる。**本人が書けない数と突き合わせる。**
    子が N で終われば外も N。シグナル s なら −s（直・sudo が自分に打ち直す）か 128+s（sh・bwrap）。"""
    if not 終わり or 終わり[0] != "終了" or code is None:
        return True
    n = 終わり[1]
    if n >= 0:
        return code == n
    return code in (n, 128 - n)


def 拒否の跡(出力, code):
    """壁に弾かれた**らしい**跡を、断定せずに拾う。

    2026-09-14、ピア daigo-6e の報告を対照つきで再現した。

        何もしない                  青 / 壁に当たった None / 終了 0
        外のファイルを消そうとした     青 / 壁に当たった None / 終了 1
        外へ curl                  青 / 壁に当たった None / 終了 6

    **壁は実際に止めている**（犠牲ファイルは残った）。止まっていないのは記録のほうで、
    「止めた回」と「何もしなかった回」の受領証が一文字も違わない。
    `壁に当たった` は資源の上限（量・CPU・大きさ・kill）しか見ておらず、
    場所と通信の拒否は EPERM としてしか返ってこないため。

    **断定はしない。**この文言は壁のせいとは限らない（元から権限の無いファイルを
    触っただけでも同じ字が出る）。だから「壁が止めた」とは書かず、**跡があることだけ**を書く。
    言い分けられないなら、言い分けられないと書く——これは
    「証明できない壁は無いものとして扱う」の裏側にあたる。
    """
    印 = (("operation not permitted", "許可されていない操作"),
          ("permission denied", "許可がない"),
          ("operation not supported", "できない操作"),
          ("read-only file system", "書けない置き場"),
          ("could not resolve host", "名前が引けない"),
          ("couldn't resolve host", "名前が引けない"),
          ("connection refused", "つなげない"),
          ("network is unreachable", "網に出られない"),
          ("sandbox", "sandbox が何か言っている"))
    低 = (出力 or "").lower()
    見つけた = []
    for 語, 訳 in 印:
        if 語 in 低 and 訳 not in 見つけた:
            見つけた.append(訳)
    return 見つけた


def check_claim(receipt, claimed_paths):
    """「直した」と言われた相手が、本当に変わったかを照合する。

    2026-09-10 の事故の形： モデルは grep で0件を見たうえで、別のファイルを
    書き換えて「削除しました」と報告した。**言葉と差分を突き合わせるのは
    外側にしかできない。**"""
    touched = {c["path"] for c in receipt["差分"]["変更"]}
    touched |= {a["path"] for a in receipt["差分"]["追加"]}
    said = {os.path.relpath(real(p), receipt["作業場"]) for p in claimed_paths}
    return {"言ったのに触っていない": sorted(said - touched),
            "言っていないのに触った": sorted(touched - said)}


# ── 予告と掃除（黙りを、不在ではなく事象にする）──────────────────

# **沈黙は「無い」ことなので、あとから探しても見つからない。**
#
# 2026-09-12 の実測。`sleep 60` を走らせている親を SIGKILL した：
#
#     作業場        a.txt が残った（＝仕事は起きた）
#     受領証        どこにも無い（＝採点は起きなかった）
#     壁の中の子孫  pid 20645 / 20646 が生き残った（＝壁も解けた）
#
# **そして誰も何も知らない。**画面には何も出ず、記録も無く、
# 次に見る人には「そんな走りは無かった」ように見える。これは
# この家の壊れ方（落ちずに黙る）のいちばん純粋な形である。
# config-guard が「戻した」と言って戻していなかったのも、
# qwc-guard が毎朝 exit127 だったのも、形はこれと同じ。
#
# **無いものを見つけるには、先に「在る」と約束しておくしかない。**
# だから走り出す前に「まだ終わっていない」と書いて fsync で確定させ、
# 終わったら書き換える。**書き換わっていない記録＝黙って終わった走り。**
# これで沈黙は、探すものから、向こうから出てくるものに変わる。
#
# 約束を受領証に変えられるのは2つだけ：
#
#     自分     ふつうの終わり。**例外でも壁に当たっても必ず書く**
#     外の掃除 親が死んでいるときだけ。**生きている親のものには触らない**
#
# 担当を重ねると、直す側と見張る側が互いを障害と見なして殴り合う
# （2026-09-06、watchdog と手作業でそれを踏んだ）。だから掃除は
# 「親が死んでいる」以外では何もしない。生きているのに期限を過ぎたものは
# **殺さずに、必ず知らせる**（それは run() の壁時計が効いていない印なので、
# 掃除が肩代わりすると本当の壊れ方が隠れる）。
#
# **記録は壁の中から触れない。**~/.guardrun は作業場の外にあり、
# 規則では家の中の読みが既定で落ちているので、中からは読めも書けもしない。
# 採点される側の手が採点表に届かない——これが「嘘を前提にする」の、
# 願いではない形である。verify() の 記録 が毎回それを確かめる。

RECORDS_ENV = "GUARDRUN_RECORDS"
猶予秒 = 300          # 期限にこれだけ足してから「過ぎた」と言う。
                      # 採点（snapshot）は2万ファイルまで歩くので、
                      # 終わりぎわに数十秒かかることがある。
親の同一視秒 = 120    # 起動時刻がこれ以内なら同じ親。pid の使い回しを見分ける幅。


def _起動時計():
    """起動からの時計（秒）。壁時計が飛んでも進み方が変わらない。Linux の経過秒と同じ時計。
    無い機械（macOS の ps は壁時計で数えるので要らない）では None。"""
    if sys.platform.startswith("linux") and hasattr(time, "CLOCK_BOOTTIME"):
        try:
            return time.clock_gettime(time.CLOCK_BOOTTIME)
        except OSError:
            return None
    return None
                      # 番号が一周するには十万回の起動が要るので、
                      # 2分以内に同じ番号が別人になることは実質起きない。
記録を残す数 = 300    # 受領証の残し数。予告だけのもの（＝未完）は絶対に捨てない。


def 記録の根(根=None):
    """受領証の置き場。**作業場の外でなければならない。**"""
    if 根:
        return real(根)
    return real(os.environ.get(RECORDS_ENV) or os.path.join(HOME, ".guardrun"))


def _確定書き(path, obj):
    """停電でも残る形で置く。**書いて・fsync して・置き換えて・親も fsync。**

    途中の姿を誰にも見せないのが肝。受領証が半分書けた状態で読まれると、
    「壊れた記録」と「未完の走り」の区別がつかなくなる。"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = "%s.tmp%d" % (path, os.getpid())
    with 開く(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _読む(path):
    try:
        with 開く(path) as f:
            return json.load(f)
    except Exception:
        return None


# ── 機械の窓口（OSに聞くのは、ここだけ）──────────────────────────

# **黙りを見つける仕組みは、ほとんど算術とファイルでできている。**
# 予告を置く・受領証を書く・差し引きを出す——ここに OS 依存は無い。
# OS に聞かないと分からないのは、たった3つしかない：
#
#     機械がいつ立ち上がったか   再起動を挟んだら pid の一致は無意味になる
#     いま誰が動いているか       同じ親か・組の生き残りは居るか
#     誰がどこを掴んでいるか     作業場に居座っているものを見つける
#
# **この3つを1か所に集める。**集めておけば、別の OS へ移すときに
# 書き直す場所が「窓口」と「執行」の2つだけになる。散らばっていると、
# 移した先で**一部だけ動いて、動かない部分が黙って False を返す**
# ——それがいちばん危ない（壁が無いのに在ると思っている状態と同じ）。
#
# **聞けないことは「聞けない」と答える。**推測で埋めない。
# 測れないものがあるなら、それに依る判定は成立しないので、
# verify() がその壁を落とす。

class 機械:
    """この機械の窓口。**足すときは 測れないもの() を正直に書く。**"""

    name = "?"

    def 使えるか(self):
        return False

    def 起動時刻(self):
        """機械が立ち上がった時刻（epoch）。分からなければ None。"""
        return None

    def プロセス表(self):
        """[{pid, ppid, pgid, 状態, 経過, 命令}] を返す。分からなければ None。

        **None と [] は別物。**[] は「誰も居ない」、None は「聞けなかった」。
        取り違えると、聞けない機械で「残党は居ません」と答えてしまう。"""
        return None

    def cwd表(self):
        """{pid: いま掴んでいるディレクトリ}。分からなければ None。"""
        return None

    def 経過秒(self, pid):
        表 = self.プロセス表()
        if 表 is None:
            return None
        for p in 表:
            if p["pid"] == pid:
                return p["経過"]
        return None

    def 測れないもの(self):
        駄目 = []
        if self.起動時刻() is None:
            駄目.append("機械の起動（再起動を見分けられない）")
        if self.プロセス表() is None:
            駄目.append("プロセス表（生死と残党を見分けられない）")
        if self.cwd表() is None:
            駄目.append("作業場の掴み（組を抜けた居座りを探せない）")
        return 駄目


def _etime秒(s):
    """`ps -o etime` の「[[日-]時:]分:秒」を秒に直す。"""
    try:
        s = s.strip()
        日 = 0
        if "-" in s:
            d, s = s.split("-", 1)
            日 = int(d)
        部 = [float(x) for x in s.split(":")]
        while len(部) < 3:
            部.insert(0, 0.0)
        return 日 * 86400 + 部[0] * 3600 + 部[1] * 60 + 部[2]
    except Exception:
        return None


class Posix機械(機械):
    """`ps` で聞く。**POSIX に書いてある綴りだけを使う。**

    `-axo` は BSD の綴りで、Linux でも procps が汲んでくれるが、
    **綴りに頼るとどちらかで黙って空が返る。**`-A -o pid=,...` は
    POSIX に定義があるので、両方で同じ意味になる（macOS で 647 行、
    BSD 形式と1行しか違わないことを確認済み）。

    `etime` は秒の分解能しか無い。**pid の使い回しを見分けるには十分**
    （番号が一周するには十万回の起動が要る）だが、Linux では /proc から
    もっと細かく採れるので、あちらは別に持つ。"""

    name = "posix (ps)"

    def _ps(self):
        return shutil.which("ps") or ("/bin/ps" if os.path.exists("/bin/ps") else None)

    def 使えるか(self):
        return bool(self._ps())

    def プロセス表(self):
        ps = self._ps()
        if not ps:
            return None
        try:
            o = subprocess.run([ps, "-A", "-o",
                                "pid=,ppid=,pgid=,state=,etime=,args="],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        except Exception:
            return None
        if o.returncode != 0:
            return None
        表 = []
        for line in (o.stdout or "").splitlines():
            部 = line.split(None, 5)
            if len(部) < 5:
                continue
            try:
                pid, ppid, pgid = int(部[0]), int(部[1]), int(部[2])
            except ValueError:
                continue
            表.append({"pid": pid, "ppid": ppid, "pgid": pgid,
                       "状態": 部[3][:1], "経過": _etime秒(部[4]),
                       "命令": (部[5] if len(部) > 5 else "")})
        return 表 or None


class Darwin機械(Posix機械):
    """macOS。**cwd は lsof に聞くしかない（/proc が無い）。**"""

    name = "darwin (sysctl + ps + lsof)"

    def 使えるか(self):
        return platform.system() == "Darwin" and bool(self._ps())

    def 起動時刻(self):
        try:
            o = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout
            m = re.search(r"sec\s*=\s*(\d+)", o or "")
            return int(m.group(1)) if m else None
        except Exception:
            return None

    def cwd表(self):
        lsof = shutil.which("lsof") or ("/usr/sbin/lsof"
                                        if os.path.exists("/usr/sbin/lsof") else None)
        if not lsof:
            return None
        try:
            o = subprocess.run([lsof, "-a", "-d", "cwd", "-Fpn"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
        except Exception:
            return None
        出, いま = {}, None
        for line in (o or "").splitlines():
            if line.startswith("p"):
                try:
                    いま = int(line[1:])
                except ValueError:
                    いま = None
            elif line.startswith("n") and いま:
                出[いま] = line[1:]
        return 出 or None


class Linux機械(機械):
    """Linux。**/proc だけで済む。外の道具を1つも呼ばない。**

    2026-09-12 に実測して分かったこと：**debian:bookworm-slim には `ps` が
    無い**（procps が入っていない）。道具の有無に頼る設計は、いちばん
    小さい機械で真っ先に崩れる。/proc は常にあるので、そちらから採る。

    ついでに精度も上がる。`/proc/<pid>/stat` の 22 番目（starttime）は
    起動からのクロック刻みなので、`etime` の秒より細かい。"""

    name = "linux (/proc)"

    def 使えるか(self):
        return os.path.isdir("/proc") and os.path.exists("/proc/stat")

    def 起動時刻(self):
        try:
            with 開く("/proc/stat") as f:
                for line in f:
                    if line.startswith("btime"):
                        return int(line.split()[1])
        except Exception:
            pass
        return None

    def _uptime(self):
        try:
            with 開く("/proc/uptime") as f:
                return float(f.read().split()[0])
        except Exception:
            return None

    def プロセス表(self):
        up = self._uptime()
        if up is None:
            return None
        HZ = os.sysconf("SC_CLK_TCK") or 100
        表 = []
        try:
            名 = os.listdir("/proc")
        except OSError:
            return None
        for n in 名:
            if not n.isdigit():
                continue
            try:
                with 開く("/proc/%s/stat" % n) as f:
                    生 = f.read()
            except OSError:
                continue          # 読んでいる間に消えた。**居ないだけで異常ではない**
            # comm は括弧に囲まれていて空白を含みうるので、右端の ')' で切る
            切れ目 = 生.rfind(")")
            if 切れ目 < 0:
                continue
            後ろ = 生[切れ目 + 2:].split()
            if len(後ろ) < 20:
                continue
            try:
                pid = int(n)
                ppid, pgid = int(後ろ[1]), int(後ろ[2])
                starttime = float(後ろ[19])
            except ValueError:
                continue
            状態 = 後ろ[0][:1]
            cmd = ""
            try:
                with 開く("/proc/%s/cmdline" % n, "rb") as f:
                    cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
            except OSError:
                pass
            表.append({"pid": pid, "ppid": ppid, "pgid": pgid, "状態": 状態,
                       "経過": up - (starttime / HZ), "命令": cmd})
        return 表 or None

    def cwd表(self):
        出 = {}
        try:
            名 = os.listdir("/proc")
        except OSError:
            return None
        for n in 名:
            if not n.isdigit():
                continue
            try:
                出[int(n)] = os.readlink("/proc/%s/cwd" % n)
            except OSError:
                continue          # 他人のものは読めない。**自分のぶんだけで足りる**
        return 出 or None


class Windows機械(機械):
    """Windows。**`ps` も `/proc` も無いので、CIM に聞く。**

    聞けるもの      立ち上がった時刻（GetTickCount64）
                    プロセス表（pid・親pid・起動時刻・命令）
    **聞けないもの** プロセス組（Windows に POSIX の組は無い）
                    作業場の掴み（外から cwd を引く道が標準では無い）

    **聞けないものを推測で埋めない。**組が無いのに 0 を入れると、
    「組を抜けた孫」を数える側が黙って全部を同じ組と見なす。
    ここで None を返しておけば、verify がその壁を落とす。

    プロセス表は powershell を1回起こすので**1秒近くかかる**。
    残党を数えるところで何度も呼ばれるため、短く覚えておく
    （覚える時間は、孫が生まれて死ぬより十分短い 1 秒）。"""

    name = "windows (cim + tick)"
    _表 = None
    _表の時刻 = 0.0

    def 使えるか(self):
        return WINDOWSか and bool(self._pwsh())

    @staticmethod
    def _pwsh():
        return shutil.which("pwsh") or shutil.which("powershell")

    def 起動時刻(self):
        if ctypes is None:
            return None
        try:
            ms = ctypes.windll.kernel32.GetTickCount64()
            return int(time.time() - ms / 1000.0)
        except Exception:
            return None

    def プロセス表(self):
        if self._表 is not None and time.time() - self._表の時刻 < 1.0:
            return self._表
        ps = self._pwsh()
        if not ps:
            return None
        # **区切りは書式指定に頼らない。**`-f "{0}`t{1}"` は backtick が
        # PowerShell・YAML・python の3か所で意味を持つので、どこかで黙って
        # 化ける（2026-09-23、実際にプロセス表が空で返った）。文字を挟む。
        命令 = ("Get-CimInstance Win32_Process | ForEach-Object { "
                "[string]$_.ProcessId + '|' + [string]$_.ParentProcessId + '|' + "
                "[string][int]((Get-Date) - $_.CreationDate).TotalSeconds + '|' + "
                "[string]$_.CommandLine }")
        環境 = dict(os.environ)
        環境.pop("PSModulePath", None)   # 親の読み込み先を持ち込まない
        try:
            o = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", 命令],
                               capture_output=True, text=True, timeout=60,
                               errors="replace", env=環境)
        except Exception:
            return None
        if o.returncode != 0 and not (o.stdout or "").strip():
            return None
        表 = []
        for 行 in (o.stdout or "").splitlines():
            部 = 行.split("|", 3)
            if len(部) < 3:
                continue
            try:
                表.append({"pid": int(部[0]), "ppid": int(部[1]),
                           # **組は無い。**0 を入れると「みんな同じ組」になる
                           "pgid": None,
                           "状態": "R",
                           "経過": float(部[2]),
                           "命令": (部[3] if len(部) > 3 else "")})
            except ValueError:
                continue
        if not 表:
            return None
        self._表, self._表の時刻 = 表, time.time()
        return 表

    def 測れないもの(self):
        駄目 = 機械.測れないもの(self)
        駄目.append("プロセス組（Windows に POSIX の組は無い）")
        return 駄目


機械たち = [Linux機械(), Darwin機械(), Windows機械(), Posix機械()]


def いまの機械():
    """この機械の窓口を選ぶ。**必ず何か返る（最後は何も測れない窓口）。**"""
    for m in 機械たち:
        if m.使えるか():
            return m
    return 機械()


def _機械の起動():
    """機械がいつ立ち上がったか。**pid の生死より先にこれを見る。**

    再起動を挟んだら、pid が一致していても何の意味も無い（同じ番号が
    別人になっている）。ここだけは確実に「死んだ」と言い切れる。"""
    return いまの機械().起動時刻()


def _経過秒(pid):
    """その pid が動いている秒数。**地域設定に依らない形で採る。**

    `lstart` は「日  7/19 20:17:32 2026」のように設定で形が変わるので、
    文字の等号で比べると、設定を変えた日に「別人だ」と誤判定して
    **生きている走りを殺しに行く。**秒数なら算術で比べられる。

    **パターン照合はしない。**`ps` の部分一致で自分の足音を4回数えた
    事故がある（2026-09-12）。窓口は pid を鍵に引く。"""
    return いまの機械().経過秒(pid)


def _別の持ち主のpid(表):
    """signal が通らない（＝別の持ち主の）生きている pid を1つ。見つからなければ None。

    証明の「黙り」の対照に使う。見つからない機械では、その対照は試さない
    （**成立しない試験を合格にも不合格にもしない**）。Windows の os.kill は本当に殺すので使わない。"""
    if WINDOWSか:
        return 1
    for p in sorted(表 or [], key=lambda x: -(x.get("経過") or 0)):
        pid = p.get("pid")
        if not pid or pid == os.getpid():
            continue
        try:
            os.kill(pid, 0)
        except PermissionError:
            return pid
        except OSError:
            continue
    return None


def _親の生死(rec, now=None, 表=None):
    """記録の親が、いまも同じ親として生きているか。→ (生きている, 説明)

    **迷ったら「生きている」に倒す。**掃除は受領証を書いて残党を殺すので、
    死んだと誤れば生きている仕事を殺す。生きていると誤っても、
    期限を過ぎたぶんは「期限超過」として必ず知らせるので、**黙りにはならない。**
    片方の間違いは仕事を壊し、もう片方は知らせが1つ増えるだけ——だから倒す先は決まる。"""
    now = now or time.time()
    記録の起動 = rec.get("機械の起動")
    いまの起動 = _機械の起動()
    if 記録の起動 and いまの起動 and 記録の起動 != いまの起動:
        return False, "機械が再起動している（記録 %s → いま %s）" % (記録の起動, いまの起動)
    pid = rec.get("親pid")
    if not pid:
        return False, "親pid が書かれていない（予告を書いた直後に落ちた）"
    try:
        _生きているか(int(pid))
    except ProcessLookupError:
        return False, "親 pid %s が居ない" % pid
    except PermissionError:
        return False, "親 pid %s は別の持ち主のもの（番号の使い回し）" % pid
    except OSError as ex:
        return True, "生死が測れない（%s）ので生きている側に倒す" % ex
    # **ゾンビは死んでいる。**`kill(pid, 0)` はゾンビにも通る（プロセス表に
    # 残っているだけで、中身はもう無い）。macOS では launchd がすぐ拾うので
    # 見えなかったが、**親を待たない親**（container の PID 1、待ち合わせを
    # しない supervisor）の下では、死んだ走りが延々「走行中」に見える
    # ——2026-09-12、Linux の container で実測。掃除が0件を返し続けた。
    # **1回の掃除は、1枚のプロセス表で判断する。**記録ごとに撮り直すと、
    # 同じ掃除の中で「Aは生きていた／Bのときにはもう死んでいた」が混ざり、
    # あとから受領証を読んでも、どの瞬間の話なのか分からなくなる。
    行 = None
    表 = いまの機械().プロセス表() if 表 is None else 表
    for x in (表 or []):
        if x["pid"] == pid:
            行 = x
            break
    if 行 is not None and 行.get("状態") == "Z":
        return False, "親 pid %s はゾンビ（もう終わっているが、誰も拾っていない）" % pid
    経過 = 行["経過"] if 行 is not None else _経過秒(pid)
    始めた = rec.get("始めた")
    if 経過 is None or not 始めた:
        return True, "起動時刻が測れないので生きている側に倒した"
    # **保存した値どうしを比べない。動かしようのない前後関係で見る。**
    # 親は予告を書いた本人なので、**予告より前から在る**。あとから
    # 始まった別人がその番号を拾ったなら、それはもう親ではない。
    # 記録した起動時刻と突き合わせる形にすると、時計が飛んだ日に
    # 生きている親を別人と読んで、動いている仕事を殺しに行く。
    # 片側だけを見るのはそのため（遅れて始まった側だけを別人と呼ぶ）。
    # **注入した時計で身元を測らない。**etime は実物の時計で進むので、
    # 偽の now と混ぜると、生きている親を「別人」と読んで殺しに行く
    # （2026-09-12、期限超過の試験でこれを踏んだ。now+400 を渡したら
    # 凍っている親が中断と判定された）。now は期限の判断にだけ使う。
    # **時計が飛んでも身元を見誤らない。**（2026-09-24・C10）Linux では NTP が時計を10分進めると、
    # 生きている親を「予告より 600 秒あとに始まった別人」と読み、動いている走りを殺しに行った
    # （コンテナで time.time だけを進めて再現）。起動からの時計どうしで比べれば壁時計は入らない。
    起始 = rec.get("親の始まり_起動時計")
    起今 = _起動時計()
    if 起始 is not None and 起今 is not None:
        実際の始まり = 起今 - 経過
        if 実際の始まり > 起始 + 親の同一視秒:
            return False, ("pid %s は別人（予告のときの親より %.0f 秒あとに始まっている"
                           "＝番号の使い回し・起動からの時計で比べた）" % (pid, 実際の始まり - 起始))
        return True, "同じ親が生きている（起動からの時計で同じ始まり）"
    実際の始まり = time.time() - 経過
    if 実際の始まり > 始めた + 親の同一視秒:
        return False, ("pid %s は別人（予告より %.0f 秒あとに始まっている"
                       "＝番号の使い回し）" % (pid, 実際の始まり - 始めた))
    return True, "同じ親が生きている（予告の %.0f 秒前から在る）" % (始めた - 実際の始まり)


def _組の生き残り(pgid, 始めた, now=None):
    """その走りのプロセスグループに、まだ生きているものが居るか。
    → (生き残り, 探せない理由)

    **「居ない」と「聞けない」を同じ返りにしない。**空の一覧だけを返すと、
    窓口の無い機械で「残党は居ませんでした」と答えることになる。
    それは受領証に嘘を書くのと同じ。

    **pgid も使い回される。**（pgid は組長の pid なので、pid と同じ癖を持つ。）
    走り始めより前から居るものは他人なので外す。
    **自分と自分の組は絶対に含めない**——見張りが自分を殺す形になる。"""
    生き = []
    try:
        pgid = int(pgid)
    except (TypeError, ValueError):
        return 生き, None
    if pgid <= 1:
        return 生き, None
    now = now or time.time()
    自分の組 = _自分の組()
    if pgid == 自分の組:
        return 生き, None
    m = いまの機械()
    表 = m.プロセス表()
    if 表 is None:
        return 生き, "この機械ではプロセス表を読めない（%s）" % m.name
    for p in 表:
        if p["pgid"] != pgid or p["pid"] <= 1 or p["pid"] == os.getpid():
            continue
        # **ゾンビは死んでいる。**もう終わっているのに、親が拾っていないだけ。
        # 数えると「始末できなかった」と永久に言い続ける（2026-09-12、Linux の
        # container で実測。あそこでは PID 1 が拾わないので必ずゾンビが残る。
        # macOS では launchd がすぐ拾うので、この穴は一度も見えなかった）。
        if p.get("状態") == "Z":
            continue
        if p["経過"] is None:
            continue
        if (now - p["経過"]) < 始めた - 親の同一視秒:
            continue          # 走り始めより前から居る＝他人
        生き.append({"pid": p["pid"], "命令": p["命令"][:120]})
    return 生き, None


_引き取り役の名前 = {"systemd", "init", "tini", "docker-init", "launchd", "bwrap", "dumb-init", "s6-svscan"}


def _居座り(workdir, 始めた, 除く組=(), now=None):
    """作業場に居座っているものを探す。**組を抜けた側を見つけるための網。**
    → (居座り, 探せない理由)

    自分でプロセスグループを作った孫には killpg が届かず、親が即死すると
    親子の線も切れる（壁の 残党 がこれ）。**環境変数の印は効かない**
    ——`ps` は子の環境を見せない（2026-09-11 に実測、2026-09-12 に再確認）。

    残る手掛かりが**作業場を掴んだまま**であること。3つ揃ったものだけ拾う：

        cwd が作業場の下   その走りの中で生まれたものである見込み
        ppid が 1          親が死んで引き取られた＝置き去り
        走り始めより後      前から居るものは他人

    **これは壁ではない。**逃げた側が chdir すれば外れるし、掴みを見られない
    機械では何も見えない。だから 残党 の壁は ★ のままにしてある。ここでやるのは
    「見つかるものは残さない」であって、「何も生き残らない」ではない。
    名前が防げる範囲より広く聞こえないよう、呼び名も 居座り にしてある。

    ppid が 1 を条件にするのは、**本人の shell を殺さないため。**作業場で
    開きっぱなしの端末は cwd が一致するが、親は端末なので 1 にはならない。"""
    出 = []
    m = いまの機械()
    掴んでいる = m.cwd表()
    if 掴んでいる is None:
        return 出, "この機械では作業場の掴みを見られない（%s）" % m.name
    表 = m.プロセス表()
    if 表 is None:
        return 出, "この機械ではプロセス表を読めない（%s）" % m.name
    now = now or time.time()
    workdir = real(workdir)
    自分 = os.getpid()
    自分の組 = _自分の組()
    # **引き取り役は pid 1 だけではない。**（2026-09-24）systemd のユーザセッションがある Linux では、
    # 親を失ったものは `systemd --user`（subreaper）に引き取られ、ppid は 1 にならない。
    # systemd を名乗る subreaper の下で、組を抜けた孫が作業場に居座ったまま見逃され、
    # 走りのあとに書いた（Linux のコンテナで再現）。利用者の shell は親が端末なので、ここには入らない。
    命令表 = {q["pid"]: q.get("命令") or "" for q in 表}

    def 引き取り役か(ppid):
        if ppid == 1:
            return True
        頭 = (命令表.get(ppid) or "").split()
        return bool(頭) and os.path.basename(頭[0]).lstrip("-") in _引き取り役の名前
    読めなかった = 0
    for p in 表:
        pid = p["pid"]
        if pid <= 1 or pid == 自分 or p["pgid"] == 自分の組 or p["pgid"] in 除く組:
            continue
        if not 引き取り役か(p["ppid"]):
            continue                      # 親が居る＝置き去りではない
        if p.get("状態") == "Z":
            continue                      # もう死んでいる（親が拾っていないだけ）
        cwd = 掴んでいる.get(pid)
        if not cwd:
            # **掴みを見られなかったものを黙って飛ばさない。**（M4）別 uid の /proc/PID/cwd は
            # 読めないことがある。走り始めより後に生まれた置き去りだけ数えて、探せなかったと言う。
            if p["経過"] is not None and (now - p["経過"]) >= 始めた - 親の同一視秒:
                読めなかった += 1
            continue
        cwd = os.path.realpath(cwd)
        if not (cwd == workdir or cwd.startswith(workdir + os.sep)):
            continue
        if p["経過"] is None or (now - p["経過"]) < 始めた - 親の同一視秒:
            continue
        出.append({"pid": pid, "命令": p["命令"][:120], "cwd": cwd})
    if 読めなかった:
        return 出, "走りのあとに生まれた置き去り %d 本は、掴んでいる場所を見られなかった（別の持ち主）" % 読めなかった
    return 出, None


def _始末(生き):
    """見つけたものを殺す。**殺せたかは、殺したあとに数え直して答える。**

    **別 uid のものには人の signal が届かない**（uid を分けた副作用）。
    届かなかったぶんは執行に頼む——そちらはその uid になって殺せる。"""
    執行 = None
    for x in 生き:
        try:
            os.kill(x["pid"], _強く殺す())
        except PermissionError:
            if 執行 is None:
                執行 = pick_enforcer()
            執行.殺す(x["pid"])
        except OSError:
            pass
    return 生き


# ── 記録（予告 → 受領証）────────────────────────────────────

# ════════════════════════════════════════════════════════════════════
# 受領証 形式版2：期待・実測・事後（2026-09-24・母艦）
#
# ~/未踏/実測/03-受領証の設計.md の「最小の形」の実装。**今の欄は1つも消さない。**
# 掃除・訓練・印の試験が今の欄を読んでいるので、区画は横に足す。
#
#   期待  走らせる前に外側が宣言して、予告に確定させる。**宣言が無ければ「未宣言」**
#         （色から後で埋めない。埋めると照合が自分の答えを写すだけになる）
#   実測  起動資料（版・OS・身元）と初期資料（走る前の作業場を丸ごと）と段階の記録
#   事後  期待との照合（一致／不一致／未宣言）と、落ちたときの traceback
#
# 97件の実績が1件も照合できなかったのは、期待と走る前の状態が無かったから
# （01-現行の固定.md）。これが入って初めて「N件中M件が期待どおり」と言える。
# ════════════════════════════════════════════════════════════════════
形式版 = 2
try:
    with open(__file__, "rb") as _f:
        _本体の指紋 = hashlib.sha256(_f.read()).hexdigest()
except (OSError, NameError):
    _本体の指紋 = None
初期資料の上限 = 64 * 1024 * 1024     # 作業場の写しの上限。この家のソースは全部で 4.9MB
_段階の番号 = {}


def _起動資料(執行名):
    """どの版の guardrun が、どの機械で、誰として走らせたか。**外側が書く。**"""
    def 取る(f):
        try:
            return f()
        except Exception:
            return None
    return {
        "取得状態": "取得済み",
        "guardrun_sha256": _本体の指紋,
        "執行": 執行名,
        "OS": 取る(platform.platform),
        "python": sys.version.split()[0],
        "uid": 取る(os.getuid) if hasattr(os, "getuid") else None,
        "gid": 取る(os.getgid) if hasattr(os, "getgid") else None,
        "umask": 取る(lambda: (lambda m: (os.umask(m), m)[1])(os.umask(0))),
        "呼び出し": list(sys.argv),
    }


def 段階(d, 名, **中身):
    """段階の記録を1行足して確定させる（fsync）。**開始しか無ければ完了を推定しない。**"""
    if not d:
        return
    n = _段階の番号.get(d, 0) + 1
    _段階の番号[d] = n
    行 = dict(連番=n, 時刻=time.time(), 単調=time.monotonic(), 段階=名, **中身)
    try:
        with open(os.path.join(d, "段階.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(行, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def _初期資料を採る(d, workdir):
    """走る前の作業場を、中身・構造・リンク・所有者・mode ごと tar に写す。

    **採点の before とは別物。**before は行数と指紋しか持たず、中身を戻せない。
    これは「同じ条件で走らせ直す」ための復元資料。リンクは辿らない。
    読めない物・上限を超えた物は、黙って飛ばさず「欠落」に名前を残す。"""
    import tarfile
    段階(d, "初期資料・始め")
    t0 = time.time()
    先 = os.path.join(d, "初期資料.tar.gz")
    欠落, 件数, 量 = [], 0, 0
    try:
        with tarfile.open(先, "w:gz") as tf:
            for 根, dirs, files in os.walk(workdir, followlinks=False):
                dirs.sort()
                for 名 in sorted(dirs) + sorted(files):
                    p = os.path.join(根, 名)
                    相対 = os.path.relpath(p, workdir)
                    try:
                        st = os.lstat(p)
                        if stat.S_ISREG(st.st_mode) and 量 + st.st_size > 初期資料の上限:
                            欠落.append("%s（上限 %dMB を超える）" % (相対, 初期資料の上限 >> 20))
                            continue
                        tf.add(p, arcname=相対, recursive=False)
                        件数 += 1
                        if stat.S_ISREG(st.st_mode):
                            量 += st.st_size
                    except (OSError, tarfile.TarError) as ex:
                        欠落.append("%s（%s）" % (相対, type(ex).__name__))
        h = hashlib.sha256()
        with open(先, "rb") as f:
            for 塊 in iter(lambda: f.read(1 << 20), b""):
                h.update(塊)
        結果 = {"取得状態": "取得済み", "参照": 先, "sha256": h.hexdigest(),
                "件数": 件数, "バイト": 量, "欠落": 欠落,
                "秒": round(time.time() - t0, 3),
                "持たないもの": ["ACL", "拡張属性", "ハードリンクの対応"]}
    except Exception as ex:                                   # noqa: BLE001
        結果 = {"取得状態": "取得失敗", "理由": "%s: %s" % (type(ex).__name__, ex),
                "欠落": 欠落}
    段階(d, "初期資料・終わり", 取得状態=結果["取得状態"])
    return 結果


def _集合(xs):
    return sorted({(x.get("path") if isinstance(x, dict) else str(x)) for x in (xs or [])})


def 照合する(期待, r):
    """事前の期待と、実際の受領証を突き合わせる。**期待が無ければ「未宣言」で止める。**

    見るのは宣言された項目だけ。宣言していない項目を「一致」に数えない
    （見た項目を必ず並べる）。"""
    if not 期待 or not 期待.get("結果"):
        return {"結果": "未宣言", "見た項目": []}
    e = 期待["結果"]
    食い違い, 見た = [], []
    if "判定" in e:
        見た.append("判定")
        許す = e["判定"] if isinstance(e["判定"], (list, tuple)) else [e["判定"]]
        if r.get("判定") not in 許す:
            食い違い.append("判定: 期待 %s／実際 %s" % ("・".join(許す), r.get("判定")))
    if "終了コード" in e:
        見た.append("終了コード")
        許す = e["終了コード"] if isinstance(e["終了コード"], (list, tuple)) else [e["終了コード"]]
        if r.get("終了コード") not in 許す:
            食い違い.append("終了コード: 期待 %s／実際 %s"
                          % ("・".join(map(str, 許す)), r.get("終了コード")))
    for 種 in ("追加", "削除", "変更"):
        if 種 in e.get("差分", {}):
            見た.append("差分." + 種)
            期 = sorted(set(map(str, e["差分"][種])))
            実 = _集合((r.get("差分") or {}).get(種))
            if 期 != 実:
                食い違い.append("差分.%s: 期待 %s／実際 %s" % (種, 期, 実))
    return {"結果": "不一致" if 食い違い else "一致", "食い違い": 食い違い, "見た項目": 見た}


_期待の判定 = ("緑", "青", "失敗", "中断", "拒否", "赤")


def _期待の形を確かめる(期待):
    """**知らない欄は断る。**照合する() は知っている欄しか見ないので、綴りを誤った欄は
    黙って見られず、見た項目の少ない「一致」になる。宣言した本人がそれに気づけない。"""
    if not isinstance(期待, dict) or not 期待:
        raise ValueError("期待は空でない JSON のオブジェクトにする")
    余り = set(期待) - {"判定", "終了コード", "差分"}
    if 余り:
        raise ValueError("知らない欄: %s（使えるのは 判定・終了コード・差分）" % "・".join(sorted(余り)))
    if "判定" in 期待:
        判 = 期待["判定"] if isinstance(期待["判定"], list) else [期待["判定"]]
        if not 判 or any(x not in _期待の判定 for x in 判):
            raise ValueError("判定は %s のどれか: %r" % ("・".join(_期待の判定), 期待["判定"]))
    if "終了コード" in 期待:
        終 = 期待["終了コード"] if isinstance(期待["終了コード"], list) else [期待["終了コード"]]
        if not 終 or any(not isinstance(x, int) or isinstance(x, bool) for x in 終):
            raise ValueError("終了コードは整数か整数の並び: %r" % (期待["終了コード"],))
    if "差分" in 期待:
        差 = 期待["差分"]
        if not isinstance(差, dict) or not 差 or set(差) - {"追加", "削除", "変更"}:
            raise ValueError("差分は 追加・削除・変更 のどれかを持つオブジェクト: %r" % (差,))
        for 種, 並び in 差.items():
            if not isinstance(並び, list) or any(not isinstance(x, str) for x in 並び):
                raise ValueError("差分.%s は文字列の並び: %r" % (種, 並び))


def _期待を固める(期待, 宣言者=None):
    """外側の宣言を予告に入れる形にする。**中身は写すだけで、ここで作らない。**"""
    if not 期待:
        return {"取得状態": "未宣言"}
    return {"取得状態": "取得済み", "結果": dict(期待),
            "宣言者": 宣言者 or "run() の呼び出し側", "宣言した時刻": time.time()}



def 予告する(workdir, argv, 執行名, 見込み, wall_sec, 根=None):
    """走り出す前に「まだ終わっていない」と書く。**これが黙りの検知器の全部。**

    ここで確定させておかないと、このあと何が起きても誰にも分からない。
    予告は**仕事を1バイトも始める前に**置く（契約が作れなくても置く。
    走らなかったことも記録に値するし、走らなかったふりも防げる）。"""
    id = "%s-%d-%s" % (time.strftime("%Y%m%d-%H%M%S"), os.getpid(),
                       os.urandom(3).hex())
    # **置き場は自分で 700 にする。**外の設定手順に任せると、任せた先が
    # 走らなかった機械で黙って緩む。2026-09-12、Linux で 755 のまま作られ、
    # 別 uid から受領証が読めた（uid を分けた意味が半分消えていた）。
    # 緩んでいたら締め直す——一度作ったあとに誰かが緩めることもある。
    base = 記録の根(根)
    try:
        os.makedirs(base, mode=0o700, exist_ok=True)
        if (os.stat(base).st_mode & 0o777) != 0o700:
            os.chmod(base, 0o700)
    except OSError:
        pass
    d = os.path.join(base, "runs", id)
    いま = time.time()
    経過 = _経過秒(os.getpid())
    約束 = {
        "id": id, "状態": "準備",
        "作業場": workdir, "命令": list(argv), "執行": 執行名, "見込み": 見込み,
        "始めた": いま, "始めた時刻": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "壁時計秒": wall_sec, "期限": いま + wall_sec + 猶予秒,
        "親pid": os.getpid(),
        # **親がいつ始まったか。**pid だけでは番号の使い回しと区別できない。
        "親の始まり": (いま - 経過) if 経過 is not None else None,
        # **起動からの時計で見た親の始まり。**（2026-09-24・C10）Linux の経過秒は /proc/uptime
        # （起動からの時計）で進むので、壁時計で見た「親の始まり」とは、時計が飛んだ日にずれる。
        # 同じ時計どうしで比べられるよう、起動からの時計の値も書いておく（無い機械では None）。
        "親の始まり_起動時計": (_起動時計() - 経過) if 経過 is not None and _起動時計() is not None else None,
        "子pid": None, "子pgid": None,
        "機械の起動": _機械の起動(),
    }
    _確定書き(os.path.join(d, "予告.json"), 約束)
    return d, 約束


def 予告を更新(d, 約束, **上書き):
    約束.update(上書き)
    _確定書き(os.path.join(d, "予告.json"), 約束)
    return 約束


def 受領証を残す(d, 受領証, 状態="終了"):
    """受領証を確定させる。**これが書かれた瞬間に、その走りは黙らなくなる。**"""
    if not d:
        return 受領証
    r = dict(受領証)
    r.pop("_出力", None)
    r.setdefault("id", os.path.basename(d))   # 置き場の名前がそのまま id
    # **形式版2の区画。**期待と起動資料・初期資料は予告に確定させてあるので、
    # 掃除が決着させる中断もここを通れば同じ照合が付く。
    約束 = _読む(os.path.join(d, "予告.json")) or {}
    r["形式版"] = 形式版
    r["期待"] = 約束.get("期待") or {"取得状態": "旧版未記録" if "期待" not in 約束 else "未宣言"}
    実測 = dict(r.get("実測") or {})
    実測.setdefault("起動資料", 約束.get("起動資料") or {"取得状態": "未到達"})
    実測.setdefault("初期資料", 約束.get("初期資料") or {"取得状態": "未到達"})
    実測["段階"] = os.path.join(d, "段階.jsonl") if os.path.exists(
        os.path.join(d, "段階.jsonl")) else None
    r["実測"] = 実測
    事後 = dict(r.get("事後") or {})
    事後["照合"] = 照合する(約束.get("期待"), r)
    r["事後"] = 事後
    段階(d, "受領証", 状態=状態, 照合=事後["照合"]["結果"])
    r["状態"] = 状態
    r["終わった"] = time.time()
    r["終わった時刻"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        _確定書き(os.path.join(d, "受領証.json"), r)
        # 前の姿はもう要らない（2万ファイルぶんの大きさになる）
        try:
            os.unlink(os.path.join(d, "before.json"))
        except OSError:
            pass
        受領証["受領証"] = os.path.join(d, "受領証.json")
        受領証["id"] = r.get("id")
    except OSError as ex:
        # **書けなかったことは黙らない。**受領証を残せない走りは、
        # 走ったこと自体が消える走りなので、判定に出す。
        # **印も変える。**（2026-09-24・Codex の監査）理由を1行足すだけで緑のままだった
        # （容量切れを模して実測）。残らない受領証の「緑」は、あとで誰も確かめられない。
        受領証.setdefault("理由", []).insert(0, "受領証を書けなかった: %s" % ex)
        if 受領証.get("判定") != "中断":
            受領証["保存できなかった印"] = 受領証.get("判定")
            受領証["判定"] = "中断"
        受領証["受領証"] = None
    return 受領証


def 記録を読む(根=None, 読めない=None):
    """置き場にある記録を全部読む。→ [(ディレクトリ, 予告, 受領証 or None)]

    **読めない予告を黙って消さない。**（2026-09-24・Codex の監査）
    壊れた・権限の無い予告は一覧から落ちていたので、掃除は「見た 0 件」と答え、
    その走りは誰にも数えられなかった。`読めない` に箱を渡すと、(場所, わけ) を入れて返す。"""
    base = os.path.join(記録の根(根), "runs")
    out = []
    try:
        names = sorted(os.listdir(base))
    except OSError as ex:
        if 読めない is not None and os.path.lexists(base):
            読めない.append((base, "置き場を並べられない（%s）" % (ex.strerror or type(ex).__name__)))
        return out
    for n in names:
        d = os.path.join(base, n)
        予告の道 = os.path.join(d, "予告.json")
        約束 = _読む(予告の道)
        if not 約束:
            if 読めない is not None and os.path.lexists(予告の道):
                読めない.append((d, "予告が読めない（壊れているか、権限が無い）"))
            continue
        out.append((d, 約束, _読む(os.path.join(d, "受領証.json"))))
    return out


def _古いのを捨てる(根=None, 残す=None):
    """終わった記録を古い順に捨てる。**未完のものは絶対に捨てない。**

    捨ててしまうと、黙って終わった走りが「無かったこと」に戻る。"""
    残す = 記録を残す数 if 残す is None else 残す
    済み = [(os.path.getmtime(os.path.join(d, "受領証.json")), d)
            for d, _y, r in 記録を読む(根) if r]
    済み.sort()
    捨てた = 0
    for _t, d in 済み[:max(0, len(済み) - 残す)]:
        shutil.rmtree(d, ignore_errors=True)
        捨てた += 1
    return 捨てた


# ── 掃除（外側から黙りを見つける）──────────────────────────────

def sweep(根=None, kill=True, now=None, 残す=None):
    """約束が受領証に変わっていない走りを、外側から見つけて決着させる。

    **これは run() の代わりではない。**親が生きている走りには触らない。
    やるのは3つだけ：

        親が死んでいる      → 前後の差分から受領証を作り、残党を始末する
        親が生きて期限超過  → 何もしない。**必ず知らせる**（壁時計が効いていない印）
        古い受領証          → 捨てる（未完のものは捨てない）

    **「中断」は失敗ではなく事実である。**中で何が起きたかは差分が答える
    （その走りが何を書いたかは、親が死んでも作業場に残っている）。"""
    now = now or time.time()
    結果 = {"見た": 0, "走行中": [], "期限超過": [], "中断": [], "捨てた": 0,
            "置き場": os.path.join(記録の根(根), "runs"), "読めない予告": []}
    記録たち = 記録を読む(根, 結果["読めない予告"])
    プ表 = いまの機械().プロセス表()          # この掃除ぜんぶで同じ1枚を使う
    # **生きている走りの組は、絶対に触らない側に置く。**同じ作業場で
    # 別の走りが動いていることがあるので、作業場で探す網に掛かってしまう。
    生きている組 = set()
    for _d, 約, 受 in 記録たち:
        if not 受 and 約.get("子pgid") and _親の生死(約, now, プ表)[0]:
            生きている組.add(int(約["子pgid"]))
    for d, 約束, 受領 in 記録たち:
        if 受領:
            continue
        結果["見た"] += 1
        生きている, なぜ = _親の生死(約束, now, プ表)
        短い = {"id": 約束.get("id"), "作業場": 約束.get("作業場"),
                "命令": 約束.get("命令"), "始めた時刻": 約束.get("始めた時刻"),
                "理由": なぜ}
        if 生きている:
            過ぎた = now - (約束.get("期限") or 0)
            if 過ぎた > 0:
                短い["超過秒"] = round(過ぎた)
                結果["期限超過"].append(短い)
            else:
                結果["走行中"].append(短い)
            continue
        結果["中断"].append(
            _中断として決着(d, 約束, なぜ, kill, now, 短い, 生きている組))
    結果["捨てた"] = _古いのを捨てる(根, 残す)
    return 結果


def _中断として決着(d, 約束, なぜ, kill, now, 短い, 生きている組=()):
    """親が死んだ走りに、受領証を作る。**採点はここでも算術だけ。**"""
    workdir = 約束.get("作業場")
    before = _読む(os.path.join(d, "before.json"))
    理由 = ["親が死んだまま終わっていない（%s）" % なぜ]
    if before is None:
        差分 = {"追加": [], "削除": [], "変更": []}
        印 = "不明"
        理由.append("前の状態が記録される前に落ちたので、差し引きが出せない")
    else:
        # JSON にすると tuple は list になるので戻す（ハッシュ比較に使う）
        before = {k: tuple(v) for k, v in before.items()}
        try:
            差分 = diff(before, snapshot(workdir))
            印, わけ = verdict(差分)
            理由 += わけ
        except OSError as ex:
            差分 = {"追加": [], "削除": [], "変更": []}
            印 = "不明"
            理由.append("作業場が読めない（%s）" % ex)
    始めた = 約束.get("始めた") or now
    生き, 組を探せない = _組の生き残り(約束.get("子pgid"), 始めた, now)
    if 組を探せない:
        理由.append(組を探せない)
    # 親子の線で辿れるぶんも足す（親が死ぬと線は切れるが、まだ残っていることがある）
    if 約束.get("子pid"):
        既知 = {x["pid"] for x in 生き}
        for pid in _子孫(int(約束["子pid"])):
            if pid not in 既知:
                生き.append({"pid": pid, "命令": "（子孫として辿った）"})
    # **組を抜けた側は、作業場を掴んだままかどうかで探す。**
    # ここで拾えなくても壁が破れたわけではない（拾える網が細いだけ）ので、
    # 探せなかったことは理由に書いて、判定は変えない。
    既知 = {x["pid"] for x in 生き}
    居座り, 探せない = _居座り(workdir, 始めた, 除く組=生きている組, now=now)
    for x in 居座り:
        if x["pid"] not in 既知:
            x = dict(x); x["命令"] = "（作業場を掴んだまま）" + x["命令"]
            生き.append(x)
    if 探せない:
        理由.append(探せない)
    残党 = {"見つけた": [x["pid"] for x in 生き], "殺した": [], "生き残った": []}
    if 生き and kill:
        _始末(生き)
        time.sleep(0.3)
        まだ = {x["pid"] for x in
                _組の生き残り(約束.get("子pgid"),
                              約束.get("始めた") or now, now)[0]}
        まだ |= {x["pid"] for x in
                 _居座り(workdir, 始めた, 除く組=生きている組, now=now)[0]}
        残党["殺した"] = [p for p in 残党["見つけた"] if p not in まだ]
        残党["生き残った"] = sorted(まだ)
        if 残党["殺した"]:
            理由.append("壁の中に残っていた %d 本を始末した" % len(残党["殺した"]))
        if 残党["生き残った"]:
            理由.append("始末できなかったものが %d 本残っている（pid %s）"
                        % (len(残党["生き残った"]),
                           "・".join(str(p) for p in 残党["生き残った"])))
    elif 生き:
        理由.append("壁の中に %d 本残っている（殺していない）" % len(生き))
    # **殺された走りの一時置き場は、ここでしか片付かない。**（2026-09-24）
    # SIGKILL された親は finally を走らせないので、証明の「黙り」を取るたびに
    # /private/tmp/guardrun-* が1個ずつ残っていた（Codex の調査・実物で確認）。
    # 消してよいのは guardrun が作った形の場所だけ（予告の値をそのまま信じない）。
    片付けの残り = []
    置き場 = 約束.get("一時置き場")
    執行 = None
    if kill and (約束.get("開けた") or 置き場):
        try:
            執行 = pick_enforcer()
        except Exception:                                # noqa: BLE001
            執行 = None
    # **親が開けた穴を外す。**（M6）一時置き場を消す前に（本人の物を消させるには穴が要る）。
    if kill and 執行 is not None and 置き場 and _片付けてよい一時置き場(置き場) and os.path.lexists(置き場):
        try:
            執行.本人の物を消す(置き場)
        except Exception:                                # noqa: BLE001
            pass
    if kill and 執行 is not None and 約束.get("開けた") and workdir:
        _開けたものを外す(執行, 約束.get("開けた"), workdir, 置き場 or "")
    if kill and 置き場 and _片付けてよい一時置き場(置き場) and os.path.lexists(置き場):
        片付けの残り = _一時置き場を消す(執行, 置き場)
        if 片付けの残り:
            理由.append("一時置き場を消せなかった: " + "／".join(片付けの残り))
    受領証 = dict(約束)
    受領証.update({
        "判定": "中断", "差分の印": 印, "差分": 差分, "理由": 理由,
        "残党": 残党, "終了コード": None, "壁に当たった": None,
        "秒": round(now - (約束.get("始めた") or now), 1),
        "掃除が作った": True,
        "片付けの残り": 片付けの残り,
    })
    残した = 受領証を残す(d, 受領証, 状態="中断")
    短い = dict(短い)
    # **書けた受領証だけを指す。**前は保存できたかを見ずに道を返していた（2026-09-24）。
    書けた = 残した.get("受領証")
    短い.update({"判定": "中断", "差分の印": 印,
                 "理由": 理由 if 書けた else ["受領証を書けなかった（決着を残せていない）"] + 理由,
                 "残党": 残党, "受領証": 書けた})
    return 短い


# ── 走らせる ──────────────────────────────────────────────────

# **人が選ばなくても走るもの。**`.git/hooks` と同じクラス。
# npm 形式のプロジェクトには同じ口が2つある：
#   package.json の install 系 script … npm install のたびに黙って走る
#   node_modules/.bin の実行可能       … あとで npm が走らせる
# 2026-09-12、ピアが実測して見つけた（postinstall は緑・.bin は青だった）。
自動で走るscript = ("preinstall", "install", "postinstall", "prepare",
                   "prepublish", "prepublishOnly", "postinstall", "postpublish")


def _自動で走る仕掛け(root):
    """あとで壁の外で勝手に走るものを集める。{名前: 中身} を返す。

    **`.git/hooks` の赤旗と同じで、完全な防御ではない。**
    package.json の scripts を全部赤にはできない（正当な scripts がある）ので、
    **人が選ばなくても走るもの**——install 系のライフサイクル——だけを見る。
    「置かれたら、あとで外で走る」のいちばん多い形を捕まえる親切である。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = os.path.basename(dirpath)
        if base == "node_modules":
            # **中は数万ファイルあるので降りない。**.bin だけ見る。
            bin_dir = os.path.join(dirpath, ".bin")
            if os.path.isdir(bin_dir):
                for name in sorted(os.listdir(bin_dir))[:2000]:
                    f = os.path.join(bin_dir, name)
                    try:
                        st = os.stat(f)
                    except OSError:
                        continue
                    if st.st_mode & 0o111:
                        out["bin:%s" % os.path.relpath(f, root)] = st.st_mtime_ns
            dirnames[:] = []
            continue
        if base in SKIP_DIRS or base == ".git":
            dirnames[:] = []
            continue
        if "package.json" in filenames:
            try:
                with 開く(os.path.join(dirpath, "package.json")) as f:
                    d = json.load(f)
                scripts = d.get("scripts") or {}
            except Exception:
                continue
            rel = os.path.relpath(os.path.join(dirpath, "package.json"), root)
            for k in 自動で走るscript:
                if k in scripts:
                    out["script:%s:%s" % (rel, k)] = str(scripts[k])
    return out


def _触った跡(root):
    """作業場の「いちばん新しい更新時刻」。**フォルダも見る。**

    書いてから消すと、ファイルは残らないが**そのフォルダの更新時刻は変わったまま残る**。
    更新時刻は操作の意図や削除の証拠ではない。差分対象外への書き込みや
    touch でも変わるので、「書いて消した」と断定してはならない。
    速さのために中身は読まない。読めない場所は飛ばす（そこは差分側が拾う）。"""
    最新 = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [None] + list(dirnames) + list(filenames):
            q = dirpath if name is None else os.path.join(dirpath, name)
            try:
                最新 = max(最新, os.lstat(q).st_mtime_ns)
            except OSError:
                pass
    return 最新


def _差分なしの理由(触った, そえ=""):
    """差分で観測していない領域を、無変更と取り違えない。"""
    範囲 = "差分対象内に変更は残っていない"
    跡 = "更新の跡はある" if 触った else "更新の跡は観測されなかった"
    return (範囲 + "・" + 跡 + そえ
            + "。対象外（dist・build・node_modules 等、大きいファイル、走査上限以降）は未判定。"
              "書いて消したか、対象外に残したか、時刻だけ変えたかは、この記録では断定できない")


def _作業場の量(root, 上限バイト=None, 上限数=None):
    """作業場の合計バイトとファイル数。**上限を超えたら早く帰る。**

    ここは SKIP_DIRS で間引かない。**採点では node_modules を見なくても、
    ディスクを食うのは同じだから。**間引くと、間引いた場所に書かれた
    ぶんが見えなくなる。"""
    total, n = 0, 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
                n += 1
            except OSError:
                pass
            if (上限バイト is not None and total > 上限バイト) or \
               (上限数 is not None and n > 上限数):
                return total, n
    return total, n


def _子孫(pid):
    """pid から辿れる子孫を全部返す。**殺す前に採るのが肝。**

    2026-09-11、ピアが実際にやって見せた：孫が自分で os.setsid() すると
    自分のプロセスグループを作るので、killpg では届かない。壁時計で
    殺したつもりのまま、裏で走り続けて印を残した。
    親が死ぬと、その孫は引き取られて親子の線が切れる。
    **だから殺す前に採る。**順番を逆にすると辿れなくなる。"""
    表 = いまの機械().プロセス表()
    if 表 is None:
        return []
    子 = {}
    for p in 表:
        子.setdefault(p["ppid"], []).append(p["pid"])
    見た, 積み = [], [pid]
    while 積み:
        いま = 積み.pop()
        for ch in 子.get(いま, []):
            if ch not in 見た:
                見た.append(ch)
                積み.append(ch)
    return 見た


# **環境変数の印で探す案は、実測で没になった。**
# ps -axeww は子の環境を見せない（この機械では sleep の行が素のまま返る）。
# 一度「見えた」と思ったのは grep が自分の命令行を数えていただけだった。
# 効かない仕掛けを残すと、それが壁に見えるので消してある。
#
# **いま残っているのは「親子で辿れるぶんだけ殺す」。**
# 自分でプロセスグループを作って親が即死する形（下の 残党 の壁）は、
# この執行では塞げない。塞ぐには専用ユーザ（kill -u が効く）が要る。


def _生きているか(pid):
    """その pid が居るか。**居なければ ProcessLookupError を上げる。**

    POSIX の `os.kill(pid, 0)` は「居るか聞くだけ」だが、**Windows では
    本当に殺す**（signal 0 が TerminateProcess になる）。見張りが見張った
    相手を殺すことになるので、Windows では OpenProcess で聞くだけにする。
    **同じ綴りが、別の OS で逆の意味を持つ。**移植でいちばん怖い形。"""
    if not WINDOWSか:
        os.kill(int(pid), 0)
        return True
    if ctypes is None:
        raise OSError("この機械では生死を聞けない")
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    h = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        誤り = ctypes.windll.kernel32.GetLastError()
        if 誤り == 5:                      # ERROR_ACCESS_DENIED＝居るが他人のもの
            raise PermissionError("pid %s は別の持ち主のもの" % pid)
        raise ProcessLookupError("pid %s が居ない" % pid)
    try:
        コード = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(コード)):
            if コード.value != STILL_ACTIVE:
                raise ProcessLookupError("pid %s は終わっている" % pid)
        return True
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def _自分の組():
    """自分のプロセス組。**Windows には組が無いので -1（＝該当なし）。**"""
    try:
        return os.getpgid(0)
    except (OSError, AttributeError):
        return -1


def _組ごと殺す(pid, 組そのもの=False):
    """その組をまとめて殺す。**Windows には組が無いので木ごと殺す。**

    POSIX は `killpg`。Windows は `taskkill /T`（子孫まで）が同じ意味に
    なる——ただし**組を抜けた孫には届かない**のは両方同じで、そこは
    執行の 皆殺し（利用者ごと）が引き受ける。"""
    if WINDOWSか:
        tk = shutil.which("taskkill")
        if not tk:
            return False
        try:
            subprocess.run([tk, "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=30)
            return True
        except Exception:
            return False
    try:
        組 = pid if 組そのもの else os.getpgid(pid)
        os.killpg(組, _強く殺す())
        return True
    except (OSError, AttributeError):
        return False


def _子の起こし方(c, e):
    """`Popen` に渡す、この機械なりの細工。**Windows に preexec_fn は無い。**

    POSIX では exec の直前に rlimit・setsid・uid を掛ける（`_limits`）。
    Windows にはその隙間が無いので、代わりに**新しいプロセス組**で起こす
    （まとめて止める口になる）。**掛けられなかった上限を「掛けたつもり」に
    しない。**量／CPU が効いているかは、verify が毎回実測で答える。"""
    if WINDOWSか:
        return {"creationflags": 0x00000200}       # CREATE_NEW_PROCESS_GROUP
    return {"preexec_fn": _limits(c, e)}


def _limits(c, e=None):
    """子に rlimit を掛け、必要なら uid を落とす。exec の前に走る。

    **順番が意味を持つ。**上限を先に掛けてから uid を落とす
    （落としたあとでは上げ直せないので、緩める方向の細工ができない）。
    `sudo` を通す道では上限が引き継がれるかどうかが実装依存なので、
    **効いているかは verify の 量／CPU が毎回答える。**"""
    落とす = e.子のuid() if e is not None else None
    かぶせ = e.子のumask() if e is not None else None

    def apply():
        # 無い機械では飛ばす。**飛ばしたことは verify の 量／CPU／時間 が
        # 実測で ★ にするので、ここで言い訳を書く必要は無い。**
        if hasattr(os, "setsid"):
            os.setsid()
        if resource is not None:
            # hard を少し上に置き、Linux でも先に SIGXCPU が届くようにする（soft=hard だと即 SIGKILL）。
            resource.setrlimit(resource.RLIMIT_CPU, (c["CPU秒"], c["CPU秒"] + 2))
            resource.setrlimit(resource.RLIMIT_FSIZE,
                               (c["1ファイル上限"], c["1ファイル上限"]))
            resource.setrlimit(resource.RLIMIT_NOFILE,
                               (c["開けるファイル数"], c["開けるファイル数"]))
        if かぶせ is not None:
            os.umask(かぶせ)
        if 落とす:
            uid, gid = 落とす
            os.setgid(gid)
            try:
                os.setgroups([gid])
            except OSError:
                pass
            os.setuid(uid)          # **ここから先は戻れない**
    return apply


def _見届けを囲う(e, argv, c, tmproot):
    """macOS は uid の起動経路を保ち、Seatbelt だけを子へ移す。"""
    command = e.囲う(argv, c, tmproot)
    inner = e.内 if isinstance(e, 重ね) else e
    if sys.platform == "darwin" and isinstance(inner, SandboxExec):
        positions = [i for i in range(len(command) - 2)
                     if command[i] == inner.BIN and command[i + 1] == "-f"]
        if len(positions) != 1:
            raise RuntimeError("Seatbelt の起動位置を一意に確認できない")
        i = positions[0]
        command = command[:i] + command[i + 3:]
    return command


def run(argv, workdir, extra_writes=(), net_allow=(),
        wall_sec=WALL_CLOCK_SEC, cpu_sec=CPU_SEC,
        max_file_bytes=MAX_FILE_BYTES, 増える見込み="ふつう",
        max_add_bytes=None, max_add_files=None,
        env=None, enforcer=None, extra_reads=(),
        require=既定の要求, prove=True, 記録=None,
        居座りも始末=True, 対話=False, 期待=None, 宣言者=None,
        初期資料=True):
    """壁の中で1回走らせて、受領証を返す。**どう終わっても受領証は必ず残る。**

    **増える見込み は人が決める。モデルの言葉から導出しないこと。**
    いまこの関数は argv からも出力からも 増える見込み を作っていない
    （2026-09-12 にピアが行単位で確認済み）。将来、呼ぶ側が利用者の
    「依存入れて」を読んで自動で "依存を入れる" を渡すようになると、
    **宣言が自己申告に化けて、仕組みごと無効になる。**
    危ないのはこの関数ではなく、この関数を呼ぶ wrapper のほうである。

    **既定では、どこにも出られない。**出先は呼ぶ側が名指しする
    （`net_allow=["localhost:11434"]`）。既定を「ollama には出られる」に
    していたのを 2026-09-12 に改めた。理由は2つ：外に出す既定は
    閉じ忘れが事故になる側で、しかも**その既定はこの家の事情**（ollama を
    使う）であって、道具の性質ではない。別の機械へ持っていくと、
    名指しを作れない執行（bwrap）では既定のまま何も走らなくなる。

    require に挙げた壁が**この機械で証明できなければ走らせない**。
    「たぶん効いている」で走らせると、効いていなかった日に何も起きない。
    証明は毎回やる（実測 20秒）。prove=False は証明そのものを試すとき用。

    **走り出す前に予告を置く。**この関数がここから先のどこで死んでも
    （例外・SIGKILL・電源断）、`~/.guardrun/runs/<id>/予告.json` だけは
    残る。受領証に変わっていない予告は、あとから sweep() が見つけて
    「中断」の受領証にする。**だから黙って終わる道が無い。**
    唯一残る穴は「記録ごと消される」形で、それは壁の中からは届かない
    （verify の 記録 が毎回確かめている）。"""
    e = enforcer or pick_enforcer()
    workdir = real(workdir)
    記録d, 約束 = 予告する(workdir, list(argv), e.name, 増える見込み,
                          wall_sec, 記録)
    # **期待と起動条件は、仕事を始める前に予告へ確定させる。**（形式版2）
    # 走ったあとに書くと、結果を見てから期待を作れてしまう。
    段階(記録d, "予告")
    約束 = 予告を更新(記録d, 約束, 期待=_期待を固める(期待, 宣言者),
                     起動条件={"取得状態": "取得済み", "run": {
                         "extra_writes": list(extra_writes), "net_allow": list(net_allow),
                         "wall_sec": wall_sec, "cpu_sec": cpu_sec,
                         "max_file_bytes": max_file_bytes, "増える見込み": 増える見込み,
                         "max_add_bytes": max_add_bytes, "max_add_files": max_add_files,
                         "env": sorted((env or {}).keys()), "extra_reads": list(extra_reads),
                         "require": list(require), "prove": prove,
                         "居座りも始末": 居座りも始末, "対話": 対話}},
                     起動資料=_起動資料(e.name))
    if 初期資料:
        約束 = 予告を更新(記録d, 約束, 初期資料=_初期資料を採る(記録d, workdir))
    else:
        約束 = 予告を更新(記録d, 約束, 初期資料={"取得状態": "対象外",
                                               "理由": "呼び出し側が 初期資料=False"})
    try:
        段階(記録d, "走る・始め")
        r = _走る(記録d, 約束, argv, workdir, extra_writes=extra_writes,
                 net_allow=net_allow, wall_sec=wall_sec, cpu_sec=cpu_sec,
                 max_file_bytes=max_file_bytes, 増える見込み=増える見込み,
                 max_add_bytes=max_add_bytes, max_add_files=max_add_files,
                 env=env, enforcer=e, extra_reads=extra_reads,
                 require=require, prove=prove,
                 居座りも始末=居座りも始末, 対話=対話)
    except BaseException as ex:
        # **例外でも黙らない。**採点の途中で落ちるのがいちばん質が悪い
        # （仕事は起きたのに、起きたという記録だけが無い状態になる）。
        import traceback
        段階(記録d, "走る・例外", 型=type(ex).__name__)
        受領証を残す(記録d, {
            "事後": {"障害": {"取得状態": "取得済み", "型": type(ex).__name__,
                              "traceback": traceback.format_exception(
                                  type(ex), ex, ex.__traceback__)}},
            "作業場": workdir, "命令": list(argv), "執行": e.name,
            "id": 約束["id"], "終了コード": None,
            "秒": round(time.time() - 約束["始めた"], 1),
            "壁に当たった": None, "判定": "中断",
            "差分": {"追加": [], "削除": [], "変更": []},
            "理由": ["採点の途中で落ちた: %s: %s" % (type(ex).__name__, ex)],
        }, 状態="中断")
        raise
    段階(記録d, "走る・終わり", 判定=r.get("判定"), 終了コード=r.get("終了コード"))
    return 受領証を残す(記録d, r)


def _他の走りが居る(記録d):
    """いま同時に走っている別の guardrun が居るか。→ その id の並び

    **皆殺しは uid ごと殺すので、同時に走る別の走りも巻き込む。**
    受領証がまだ無く、親が生きている予告を、既定の置き場・この走りの置き場・
    証明の置き場の3か所で探す。自分（同じ pid）の予告は数えない。
    **探せなかったら「居る」と答える**（巻き込むより、残すほうを選ぶ）。"""
    import glob
    根々 = {記録の根(None)}
    if 記録d:
        根々.add(os.path.dirname(os.path.dirname(記録d)))
    根々 |= set(glob.glob(os.path.join(HOME, ".guardrun-verify", "run-*", "記録")))
    居る = []
    try:
        for 根 in 根々:
            for d, 約束, 受 in 記録を読む(根):
                if 受 is not None or d == 記録d:
                    continue
                親 = 約束.get("親pid")
                if not 親 or 親 == os.getpid():
                    continue
                try:
                    _生きているか(親)
                except ProcessLookupError:
                    continue
                except OSError:
                    pass                  # 他人の持ち物＝居る
                居る.append(約束.get("id"))
    except Exception as ex:                                   # noqa: BLE001
        return ["探せなかった（%s）" % type(ex).__name__]
    return 居る


def _走る(記録d, 約束, argv, workdir, extra_writes=(),
         net_allow=(),
         wall_sec=WALL_CLOCK_SEC, cpu_sec=CPU_SEC,
         max_file_bytes=MAX_FILE_BYTES, 増える見込み="ふつう",
         max_add_bytes=None, max_add_files=None,
         env=None, enforcer=None, extra_reads=(),
         require=既定の要求, prove=True, 居座りも始末=True, 対話=False):
    """run() の中身。**予告と受領証の外側は run() が持つ。**

    ここを直接呼ばないこと。呼ぶと、黙って終われる道が1本できる。"""
    e = enforcer or pick_enforcer()

    空 = {"追加": [], "削除": [], "変更": []}
    if 増える見込み not in 増加の宣言:
        # **知らない宣言は既定に落とさない。**打ち間違いを黙って
        # 「ふつう」に落とすと、依存を入れる走りが途中で殺される。
        return {"作業場": workdir, "命令": list(argv), "執行": e.name,
                "終了コード": None, "秒": 0.0, "壁に当たった": None,
                "差分": 空, "判定": "拒否",
                "理由": ["知らない見込み %r（使えるのは %s）"
                         % (増える見込み, "・".join(増加の宣言))],
                "壁": None, "出力の長さ": 0, "_出力": ""}
    宣言B, 宣言N = 増加の宣言[増える見込み]
    max_add_bytes = 宣言B if max_add_bytes is None else max_add_bytes
    max_add_files = 宣言N if max_add_files is None else max_add_files
    try:
        要る = [d for d in e.要る書き場()
                if not real(workdir).startswith(real(d) + os.sep)]
        c = contract([workdir] + list(extra_writes) + 要る, net=list(net_allow),
                     cpu_sec=cpu_sec, wall_sec=wall_sec,
                     max_file_bytes=max_file_bytes, reads=list(extra_reads),
                     max_add_bytes=max_add_bytes, max_add_files=max_add_files,
                     記録=os.path.dirname(os.path.dirname(記録d)))
    except 契約違反 as ex:
        # **契約が作れないものは走らせない。**規則を壊す文字が入っている
        # パスは、事故ではなく攻撃の形をしている。
        return {"作業場": workdir, "命令": list(argv), "執行": e.name,
                "終了コード": None, "秒": 0.0, "壁に当たった": None,
                "差分": 空, "判定": "拒否", "理由": [str(ex)],
                "壁": None, "出力の長さ": 0, "_出力": ""}

    守れる, なぜ = e.契約を守れるか(c)
    if not 守れる:
        # **守れない契約で走らせない。**一部だけ効いた壁は、
        # 「壁がある」と思っている状態を作るので、無いより悪い。
        return {"作業場": workdir, "命令": list(argv), "執行": e.name,
                "終了コード": None, "秒": 0.0, "壁に当たった": None,
                "差分": 空, "判定": "拒否", "理由": [なぜ],
                "壁": c, "出力の長さ": 0, "_出力": ""}

    証明の古さ = None
    if prove and require:
        証明, 証明の古さ = 証明を取る(e, 証明の有効期限)
        駄目 = [w for w in require if not 証明.get(w, (False, "見ていない"))[0]]
        if 駄目:
            return {
                "作業場": workdir, "命令": list(argv), "執行": e.name,
                "終了コード": None, "秒": 0.0, "壁に当たった": None,
                "差分": {"追加": [], "削除": [], "変更": []},
                "判定": "拒否",
                "証明の古さ": round(証明の古さ or 0),
                "理由": ["%s の壁が証明できない: %s"
                         % (w, 証明.get(w, (False, "見ていない"))[1]) for w in 駄目],
                "壁": c, "証明": {k: list(v) for k, v in 証明.items()},
                "出力の長さ": 0, "_出力": "",
            }

    # **一時置き場は走るたびに作る。**共有の temp を丸ごと許すと、
    # 作業場がその下にあるときに壁が素通しになる（2026-09-11 に踏んだ）。
    tmproot = real(tempfile.mkdtemp(prefix="guardrun-", dir=e.一時の親()))
    # **一時置き場の場所を予告に書く。**この走りが SIGKILL されると finally は走らない。
    # そのとき片付けられるのは、あとで来る sweep だけ（2026-09-24）。
    if 記録d:
        予告を更新(記録d, 約束, 一時置き場=tmproot)
    # **作った直後から守る。**ここから try までの間で落ちると、一時置き場も
    # 開けた ACL も残ったままになっていた（Codex の調査）。
    用意した = False
    try:
        env = dict(env or os.environ)
        env["TMPDIR"] = env["TMP"] = env["TEMP"] = tmproot
        env = e.環境を直す(env, tmproot)
        できた, なぜ = e.用意(c, workdir, tmproot)
        用意した = True
        # **開けた穴を予告に書く。**（2026-09-24・M6）親が SIGKILL されると片付け（ACL を外す）は走らず、
        # 何を開けたかは親の記憶と一緒に消える。sweep が決着させたあとも作業場に _guardrun の ACL が
        # 残っていた（殺して再現）。書いておけば、sweep が同じ権利を外せる。
        if 記録d and できた:
            予告を更新(記録d, 約束, 開けた=_開けたものの記録(e))
        if not できた:
            # **下ごしらえができないなら走らせない。**穴を開けられないまま
            # 走らせると、作業場に書けずに落ちて、原因が分からない失敗になる。
            # 途中まで開けた穴は閉じる（前は閉じずに帰っていた）。
            try:
                e.片付け(c, workdir, tmproot)
            except Exception:                            # noqa: BLE001
                pass
            残り = _一時置き場を消す(e, tmproot)
            return {"id": 約束["id"], "作業場": workdir, "命令": list(argv),
                    "執行": e.name, "終了コード": None, "秒": 0.0,
                    "壁に当たった": None, "差分": 空, "判定": "拒否",
                    "理由": ["執行の下ごしらえができない: %s" % なぜ]
                    + (["一時置き場を消せなかった: " + "／".join(残り)] if 残り else []),
                    "片付けの残り": 残り,
                    "壁": c, "出力の長さ": 0, "_出力": ""}

        before = snapshot(workdir)
        # **前の姿をディスクに置く。**親の頭の中にしか無いと、親が死んだ瞬間に
        # 「何が変わったか」を出す土台ごと消える。作業場の中身は残っているのに
        # 差し引きが出せない——という形の黙りになる。
        _確定書き(os.path.join(記録d, "before.json"), before)
        仕掛け前 = _自動で走る仕掛け(workdir)
        元のバイト, 元の数 = _作業場の量(workdir)
        元の更新 = _触った跡(workdir)
    except BaseException:
        try:
            if 用意した:
                e.片付け(c, workdir, tmproot)
        finally:
            _一時置き場を消す(e, tmproot)
        raise
    started = time.time()
    killed = None
    止まらなかった = None
    元の受け手 = {}
    量超え = []           # 見回りの糸から本文へ渡す箱

    def 見回り(proc):
        """作業場が膨らみすぎたら殺す。

        **rlimit に合計の口が無いので、自分で測るしかない。**
        壁時計と同じ形（測って、プロセスグループごと殺す）。"""
        上限B = c["増やせるバイト"]
        上限N = c["増やせるファイル数"]
        while proc.poll() is None:
            time.sleep(量の見回り秒)
            b, n = _作業場の量(workdir, 元のバイト + 上限B, 元の数 + 上限N)
            増B, 増N = b - 元のバイト, n - 元の数
            if 増B > 上限B or 増N > 上限N:
                量超え.append("作業場を %.0fMB・%d ファイル増やした（上限 %.0fMB・%d）"
                              % (増B / 1e6, 増N, 上限B / 1e6, 上限N))
                子孫 = _子孫(proc.pid)
                try:
                    _組ごと殺す(proc.pid)
                except OSError:
                    pass
                for pid in 子孫:
                    try:
                        os.kill(pid, _強く殺す())
                    except OSError:
                        pass
                return

    かけら = []
    パイプ居残り = False
    居座り = {"見つけた": [], "殺した": [], "探せない": None}

    def 読み取る(proc):
        """出力を別の糸で吸い出す。**壁時計を出力に握らせないため。**

        2026-09-12 実測。`communicate(timeout=)` は「子が終わるまで」ではなく
        「**パイプが閉じるまで**」を測る。組を抜けた孫がそのパイプを握って
        いると、壁時計2秒と言った走りが **25.2 秒**返らなかった
        （対照＝孫の出力を /dev/null に向けた同じ走りは 2.4 秒）。
        しかも受領証には「壁に当たった: 壁時計 2 秒」と書かれる。
        **壁が破られたのではなく、破られたことを採点が隠していた。**

        いまは待つ相手を分ける：壁時計は**子の終わり**だけを測り、
        出力はこの糸が拾えたぶんだけ受け取る。取り切れなかったら、
        取れなかったと受領証に書く（黙って短い出力を返さない）。"""
        fd = proc.stdout.fileno()
        while True:
            try:
                b = os.read(fd, 65536)
            except OSError:
                break
            if not b:
                break
            かけら.append(b)

    try:
        # **対話のときは口を塞がない。**
        # 既定で stdin を閉じているのは、入力待ちで固まる道を1本消すため。
        # だが人が対話で使う道具を壁に入れるには、口が要る。
        # 出力も横取りしない（REPL の画面が壊れる）。**受領証は元々
        # 出力を使っていない**（差し引きだけで採点する）ので、何も失われない。
        # 固まりは壁時計が切る——口を開けても、黙りは塞がったまま。
        見届け役 = os.path.join(tmproot, "見届け役.py")
        with 開く(見届け役, "w") as f:
            # **sudo のあとで rlimit を掛け直す。**（2026-09-24）
            # Linux の sudo は PAM（/etc/pam.d/sudo の pam_limits）で上限を unlimited に戻す
            # （GitHub ubuntu-22.04 で実測: 親 fsize=128 → sudo -u の中 unlimited）。
            # シェルの ulimit は機械ごとに単位が違い、Mac では上げる向きになって
            # 「Operation not permitted」が出力に混ざり証明を2つ壊した。**バイト単位の python で掛ける。**
            f.write(_見届け役の中身.replace("__上限__", repr(
                (c.get("CPU秒"), c.get("1ファイル上限"), c.get("開けるファイル数")))).replace(
                "__書ける__", repr([real(x) for x in c["書ける場所"]])).replace("__MAC_PROFILE__", repr((e.内 if isinstance(e, 重ね) else e).規則(c, tmproot) if sys.platform == "darwin" and isinstance(e.内 if isinstance(e, 重ね) else e, SandboxExec) else "(version 1)(allow default)")))
        p = subprocess.Popen(
            _見届けを囲う(e, [PY, 見届け役, os.path.join(tmproot, "見届け.txt")] + list(argv), c, tmproot), cwd=workdir,
            stdout=(None if 対話 else subprocess.PIPE),
            stderr=(None if 対話 else subprocess.STDOUT),
            stdin=(None if 対話 else subprocess.DEVNULL),
            env=env, **_子の起こし方(c, e),
        )
        try:
            子組 = os.getpgid(p.pid)      # _limits() の setsid で自分の組になる
        except (OSError, AttributeError):
            # **Windows に組は無い。**pid をそのまま組として扱う。
            # まとめて止める口は執行の 皆殺し（利用者ごと）が持つ。
            子組 = p.pid
        予告を更新(記録d, 約束, 状態="走行中", 子pid=p.pid, 子pgid=子組,
                   期限=time.time() + wall_sec + 猶予秒)
        番 = threading.Thread(target=見回り, args=(p,), daemon=True)
        番.start()
        読み手 = None
        if not 対話:
            読み手 = threading.Thread(target=読み取る, args=(p,), daemon=True)
            読み手.start()
        # **対話のときは、端末のシグナルを中へ渡す。**（2026-09-24・M7）
        # 子は setsid で端末から切り離されているので、Ctrl-C は guardrun 自身に届き、
        # KeyboardInterrupt で guardrun だけが 0.4 秒で落ちて受領証も書かれず、命令は置き去りだった。
        # 渡す先は子（sudo・壁の起動役）。sudo は受けたシグナルを命令側へ中継し、見届け役が命令へ渡す。
        # Ctrl-Z は中へ渡してから自分も止まる（シェルのジョブ制御に合わせる）。fg の SIGCONT も渡す。
        元の受け手 = {}
        if 対話 and not WINDOWSか:
            # **sudo の中継に頼らない。**sudo は SIGTERM は中継するが、SIGINT と SIGTSTP は
            # kill で送っても中継しなかった（実測）。見届け役を名前（走りごとの一時置き場の道）で探し、
            # 直に送る。別 uid なら人からは送れないので、その uid として kill する。
            利用者 = next((getattr(x, "利用者", None) for x in (e, getattr(e, "外", None), getattr(e, "内", None))
                           if x is not None and getattr(x, "利用者", None) and getattr(x, "子のuid", lambda: None)() is None
                           and type(x).__name__ == "別ユーザ"), None)
            見届けpid = []

            def _見届け役のpid():
                if not 見届けpid:
                    # sudo・sandbox-exec・bwrap のコマンドラインにも見届け役の道は入る（最初は root の
                    # sudo を拾い、kill が断られた）。**python が見届け役そのものを走らせている行**だけを拾う。
                    for q in (いまの機械().プロセス表() or []):
                        語 = (q.get("命令") or "").split()
                        if len(語) >= 2 and os.path.basename(語[0]).lower().startswith("python") and 語[1] == 見届け役:
                            見届けpid.append(q["pid"])
                            break
                return 見届けpid[0] if 見届けpid else None

            def _中へ(n, _f):
                先 = _見届け役のpid()
                if 先 is None:
                    try:
                        os.kill(p.pid, n)
                    except OSError:
                        pass
                elif 利用者 and not _根か() and shutil.which("sudo"):
                    subprocess.run([shutil.which("sudo"), "-n", "-u", 利用者, "/bin/kill",
                                    "-%d" % int(n), str(先)], capture_output=True, timeout=10)
                else:
                    try:
                        os.kill(先, n)
                    except OSError:
                        pass
                if n == signal.SIGTSTP:
                    signal.signal(signal.SIGTSTP, signal.SIG_DFL)
                    os.kill(os.getpid(), signal.SIGTSTP)          # ここで止まる。fg で戻る
                    signal.signal(signal.SIGTSTP, _中へ)
            for 名 in ("SIGINT", "SIGQUIT", "SIGTERM", "SIGHUP", "SIGTSTP", "SIGCONT"):
                if hasattr(signal, 名):
                    try:
                        元の受け手[名] = signal.signal(getattr(signal, 名), _中へ)
                    except (ValueError, OSError):
                        pass
        try:
            code = p.wait(timeout=wall_sec)
        except subprocess.TimeoutExpired:
            # **孫まで始末する。**qwc が「確認のあと固まる」のは
            # 孫が残って stdio を掴んだままになるのが原因だった（2026-08-25）。
            killed = "壁時計 %d 秒" % wall_sec
            子孫 = _子孫(p.pid)          # 親子で辿れるぶん（殺す前に採る）
            # **殺せなかったことを捨てない。**（2026-09-24・Codex の監査）
            # 別 uid の組には人から signal が届かない（EPERM）ことがあり、前は全部握りつぶしていた。
            殺せなかった = []
            try:
                if _組ごと殺す(p.pid) is False:
                    殺せなかった.append("組ごと")
            except OSError as ex:
                殺せなかった.append("組ごと（%s）" % (ex.strerror or type(ex).__name__))
            for pid in 子孫:
                try:
                    os.kill(pid, _強く殺す())
                except ProcessLookupError:
                    pass
                except OSError as ex:
                    殺せなかった.append("pid %d（%s）" % (pid, ex.strerror or type(ex).__name__))
            # **uid ごと殺せる執行なら、それも打つ。**killpg と子孫辿りでは
            # 組を抜けた孫に届かない（それが 残党 の壁）。ここだけが届く。
            if e.皆殺し() is False:
                殺せなかった.append("uid ごと")
            try:
                code = p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # **止まっていないのに -9 と書かない。**前はここで code = -9 と決め打ちし、
                # 命令が生きたまま受領証は「青・時間切れで止めた」だった（殺す手を全部外して再現）。
                code = None
                止まらなかった = "壁時計で止めようとしたが止まらなかった（効かなかった手: %s）" % (
                    "・".join(殺せなかった) or "不明")
        # **子を始末したら、その場で作業場の居座りを片付ける。**
        #
        # ここが「出力を待ったあと」だと**間に合わない。**2026-09-12 実測：
        # 3秒眠って印を書く孫は、5秒の出力待ちの内側で仕事を終えていた
        # （片付けは死体を探すだけになる）。順番を入れ替えると、孫は
        # 2.2秒で止まり、印は書かれない。**待つ前に殺す。**
        #
        # 出力にも効く。パイプを握っていた当人が居なくなるので、
        # このあとの join がすぐ返る。
        #
        # **これは 残党 の壁を塞いだのではない。**探すのに 0.2 秒かかるので、
        # それより速い孫には間に合わないし、chdir されれば外れる。
        # だから壁の判定は ★ のままにしてある。拾えたぶんは受領証に数で残す。
        if 居座りも始末:
            見つけた, 探せない = _居座り(workdir, started)
            居座り["見つけた"] = [x["pid"] for x in 見つけた]
            居座り["探せない"] = 探せない
            if 見つけた:
                _始末(見つけた)
                time.sleep(0.2)
                まだ, _ = _居座り(workdir, started)
                まだpid = {x["pid"] for x in まだ}
                居座り["殺した"] = [p for p in 居座り["見つけた"]
                                    if p not in まだpid]
                居座り["生き残った"] = sorted(まだpid & set(居座り["見つけた"]))
            # **ふつうに終わった走りでも、壁の利用者のものは全部片付ける。**（2026-09-24・母艦）
            # 前は皆殺しを壁時計で止めたときにしか打っていなかった。作業場で探す網は
            # 別の uid のものの cwd を見られず（見つけた: []）、組を抜けた孫が
            # _guardrun の持ち物として ppid 1 で生き残っていた（guardrun-実測 で発見・
            # sleep 300 が走りのあとも居た）。証明の 残党 が ○ だったのは、証明の試験が
            # 壁時計の道で測っていたから＝**本番の道を測っていなかった**。
            # 同時に走る別の走りが居れば巻き込むので、そのときは打たずに書き残す。
            if not killed:
                他 = _他の走りが居る(記録d)
                if 他:
                    居座り["皆殺し"] = "見送った（同時に走っている: %s）" % "・".join(map(str, 他))
                else:
                    打 = e.皆殺し()
                    居座り["皆殺し"] = ("打った" if 打 not in (None, False)
                                        else "打てなかった（sudo か pkill が断った）" if 打 is False
                                        else "この執行では打てない")
        if 読み手 is not None:
            読み手.join(出力の待ち秒)
            パイプ居残り = 読み手.is_alive()
            try:
                p.stdout.close()
            except OSError:
                pass
        out = b"".join(かけら).decode("utf-8", "replace")
    finally:
        # 対話のあいだだけ差し替えたシグナルの受け手を戻す（呼んだ側の Ctrl-C の効き方を変えない）
        for 名, 受 in 元の受け手.items():
            try:
                signal.signal(getattr(signal, 名), 受)
            except (ValueError, OSError, TypeError):
                pass
        # **片付けは、記録の読み取りがどう落ちても必ず走らせる。**
        起動した, 終わり, 閉じ込め = False, None, None
        try:
            起動した, 終わり = _見届けを読む(os.path.join(tmproot, "見届け.txt"))
            閉じ込め = _閉じ込めを読む(os.path.join(tmproot, "見届け.txt"))
        finally:
            # 本人の物は ACL を外す前に消させる（外すと本人が入れない）
            try:
                e.本人の物を消す(tmproot)
            except Exception:                            # noqa: BLE001
                pass
            try:
                e.片付け(c, workdir, tmproot)
            finally:
                片付けの残り = _一時置き場を消す(e, tmproot)

    elapsed = time.time() - started
    d = diff(before, snapshot(workdir))
    mark, reasons = verdict(d)
    if パイプ居残り:
        # **短い出力を黙って返さない。**出力が途中で切れたことと、
        # 相手が何も言わなかったことは別物で、取り違えると原因を見失う。
        reasons = reasons + ["出力を最後まで取れなかった"
                             "（組を抜けたものがパイプを握っている）"]
    if 居座り["殺した"]:
        # **黙って片付けない。**組を抜けたものが居たという事実は、
        # 壁の 残党 が効いていないことの実例なので、受領証に残す。
        reasons = reasons + ["走り終わったあと、作業場に居座っていた %d 本を始末した"
                             % len(居座り["殺した"])]

    # **増えすぎは、止められなくても必ず見つける。**
    # 見回りは1秒ごとだが、5,000ファイルは 0.2 秒で書ける（実測）。
    # 速い一気書きに見回りは間に合わない。**だから壁と採点を分ける。**
    #   壁   … 長く続く増えかたは止める（best effort）
    #   採点 … 速かろうと遅かろうと、増えた事実は必ず赤にする
    # **あとで壁の外で勝手に走るものが増えていないか。**
    仕掛け後 = _自動で走る仕掛け(workdir)
    新しい仕掛け = [k for k, v in 仕掛け後.items() if 仕掛け前.get(k) != v]
    if 増える見込み != "ふつう":
        # 依存を入れる走りでは .bin が増えるのは正常（npm が作る）。
        # **script のほうは、依存を入れても増えないのが正常。**
        新しい仕掛け = [k for k in 新しい仕掛け if not k.startswith("bin:")]
    if 新しい仕掛け:
        mark = "赤"
        reasons = ["あとで壁の外で走るものが増えた: %s"
                   % "・".join(k.split(":", 1)[1] for k in 新しい仕掛け[:5])] + reasons

    触った = _触った跡(workdir) > 元の更新
    後のバイト, 後の数 = _作業場の量(workdir)
    増B, 増N = 後のバイト - 元のバイト, 後の数 - 元の数
    if 増B > c["増やせるバイト"] or 増N > c["増やせるファイル数"]:
        mark = "赤"
        reasons = ["作業場が %.0fMB・%d ファイル増えた"
                   "（見込み『%s』の上限 %.0fMB・%d）"
                   % (増B / 1e6, 増N, 増える見込み, c["増やせるバイト"] / 1e6,
                      c["増やせるファイル数"])] + reasons

    # 壁に当たったこと自体は失敗ではない。**壁が働いた証拠である。**
    最大ファイル = _最大のファイル(workdir)
    hit = _hitを決める(終わり, code, 量超え, killed, cpu_sec, max_file_bytes, 最大ファイル)

    # **「止めた」と「何もしなかった」を、受領証の上で分ける。**
    # 断定できないので、分けるのは「跡」と「言い分けられない」という一文まで。
    跡 = 拒否の跡(out, code)

    # **中身が落ちた走り・壁が立たなかった走り・失敗した走りを「青」にしない。**（2026-09-23）
    # 青は「走って、ふつうに終わって、何も変えなかった」だけ。決めるのは見届け役の記録。
    #   起動が無い           … 壁の中に届いていない（壁か、その手前の sudo/sh が立たなかった）→ 拒否
    #   起こせない           … 壁は立ったが命令が起動できない（名前違いなど）→ 失敗
    #   シグナルで終わった    … 中断
    #   終了 ≠ 0            … 失敗（本人の決定：exit≠0 で差分が空は、青でも中断でもない別の印）
    #   起動したが終わりが無い … 見届け役ごと止められた → 中断
    # 壁の上限で止めた回（hit あり）は壁が働いた証拠なので、ここでは触らない。
    # **終了コードは変えない**（qwc は子の終了コードを返す＝呼ぶ側の約束はそのまま）。変えるのは印と理由だけ。
    見届け = {"起動": 起動した, "終わり": list(終わり) if 終わり else None,
              "閉じ込め": 閉じ込め}
    if mark in ("青", "緑") and hit is None and not _記録と終了コードが合うか(終わり, code):
        mark = "中断"
        reasons = ["見届けの記録（終了 %s）と実際の終了コード（%s）が食い違う——"
                   "記録が書き換えられたか、見届け役ごと止められた" % (終わり[1], code)] + reasons
    elif mark in ("青", "緑") and hit is None and 起動した == "差し替え":
        mark = "中断"
        reasons = ["見届けの記録が普通のファイルでなくなっていた（FIFO やリンクに差し替えられた）"
                   "——終わり方を確かめられない"] + reasons
    elif mark == "緑" and hit is None and not (終わり and 終わり[0] == "終了" and 終わり[1] == 0):
        # **書いたうえで失敗した走りを「緑」にしない。**（2026-09-24・本人の決定）
        # 途中まで書いて落ちた走り（ファイルの上限に当たって EFBIG で exit 1 など）が、
        # 差分があるというだけで緑になっていた。書いた中身は差分にそのまま残る。
        if 終わり is None:
            mark = "中断"
            reasons = ["書き換えはあるが、壁の中の見届け役が終わり方を残していない"
                       "（終了コード %s）——途中で止められたか、記録が消された" % code] + reasons
        elif 終わり[0] == "終了" and 終わり[1] < 0:
            mark = "中断"
            reasons = ["書き換えの途中で命令が異常終了した（シグナル %d・終了コード %s）"
                       % (-終わり[1], code)] + reasons
        else:
            mark = "失敗"
            reasons = ["書き換えはあるが、命令は失敗で終わった（%s）"
                       % ("終了コード %d" % 終わり[1] if 終わり[0] == "終了" else "起動できない")] + reasons
    elif mark == "青" and hit is None:
        頭 = next((x.strip()[:200] for x in (out or "").splitlines() if x.strip()), "")
        if not 起動した:
            mark, reasons = "拒否", ["見届けの記録に起動が無い——壁の中に届かなかったか、"
                                     "中の命令が記録を消した"
                                     + (": " + 頭 if 頭 else "")]
        elif 終わり is None:
            mark = "中断"
            reasons = ["壁の中の見届け役ごと止まった（終わり方の記録が無い・終了コード %s）" % code]
        elif 終わり[0] == "起こせない":
            mark, reasons = "失敗", ["命令を起動できなかった（%s）" % 終わり[1]]
        elif 終わり[1] < 0:
            mark = "中断"
            reasons = (["命令が異常終了した（シグナル %d・終了コード %s）——何も変わっていないのは、"
                        "仕事を終えたからではない" % (-終わり[1], code)]
                       + (["拒否の跡: " + " / ".join(跡)] if 跡 else []))
        elif 終わり[1] != 0:
            mark = "失敗"
            reasons = (["命令が失敗で終わった（終了コード %d）・何も変わっていない" % 終わり[1]]
                       + (["作業場に触った跡はある（書いてから消した）"] if 触った else [])
                       + (["拒否の跡: " + " / ".join(跡)] if 跡 else []))
    if mark == "青":
        # **「何も変わっていない」を2つに割る。**（2026-09-23）
        # 走る前と後でフォルダの更新時刻を比べると、書いてから消した回は跡が残る。
        # 終了コードで入口を作らないこと——壁が書き込みを止めても、
        # `sh` が飲み込んで終了コード0で帰る回がある（同日、実測）。
        言い分 = []
        if code not in (0, None):
            言い分.append("終了コード %s" % code)
        if 跡:
            言い分.append("拒否の跡: " + " / ".join(跡))
        そえ = ("（%s）" % "・".join(言い分)) if 言い分 else ""
        reasons = [_差分なしの理由(触った, そえ)]

    # **壁時計で止めた走りは、緑にしない。青（壁が働いた）にして、終わっていないと書く。**
    # （2026-09-24・母艦が本人の代わりに決めた。本人が違う判断をしたらそちらを優先）
    # 中断は「guardrun 自身が最後まで見届けられなかった」印なので、壁が止めた場合とは混ぜない。
    # 赤は赤のまま（削除・仕掛け・量の超過のほうが重い）。
    if 止まらなかった:
        # 壁時計で止めたと言えない。guardrun が最後まで見届けられなかった＝中断。
        mark = "中断"
        reasons = [止まらなかった] + reasons
    elif hit and str(hit).startswith("壁時計") and mark in ("緑", "青", "失敗", "中断"):
        mark = "青"
        reasons = ["時間切れで止めた・終わっていない（%s）" % hit] + [
            x for x in reasons if not x.startswith("何も変わっていない")]
    if 片付けの残り:
        reasons = reasons + ["一時置き場を消せなかった: " + "／".join(片付けの残り)]
    return {
        "id": 約束["id"],
        "作業場": workdir, "命令": list(argv), "執行": e.name,
        "終了コード": code, "秒": round(elapsed, 1), "壁に当たった": hit,
        "拒否の跡": 跡,
        # **壁の通信をどこまで緩めた走りか。**外（localhost 以外）を名指しした走りは名前も引ける（2026-09-25）
        "外へ出られる": [t for t in c["出られる先"] if t.split(":")[0] not in ("localhost", "127.0.0.1", "::1")],
        "見届け": 見届け,
        # **消せなかった一時置き場を黙らない。**印は変えない（命令のせいではないので）。
        "片付けの残り": 片付けの残り,
        "差分": d, "判定": mark, "理由": reasons, "壁": c,
        # **足した材料は、何回出たかを数えられるようにしておく。**
        # 出ない印は優秀なのではなく、試されていないだけ（2026-09-23・ピアの指摘）。
        "触った跡": 触った,
        "見込み": 増える見込み, "居座り": 居座り,
        # **使い回した証明で走ったなら、何秒前のものかを残す。**
        "証明の古さ": (None if 証明の古さ is None else round(証明の古さ)),
        "出力の長さ": len(out or ""),
        "_出力": out or "",     # 頭の _ は「数ではない」印
    }


def 壁の利用者を作る():
    """Windows に壁の利用者を1人作り、合言葉を人だけが読める所に置く。

    **管理者で1回だけ走らせるもの。**macOS / Linux の
    `guardrun-user-setup`（uid を作る）に当たる。

    合言葉が要るのは、Windows に `sudo -n`（合言葉なしで別人になる道）が
    無いから。**置き場は人だけが読める形にして、壁の中から読めないことを
    証明が毎回見る**（読めたら 秘密 が ★ になる）。"""
    if not WINDOWSか:
        print("これは Windows のための口です（macOS/Linux は guardrun-user-setup）")
        return 1
    e = Windows別ユーザ()
    if not _根か():
        print("管理者で走らせてください（利用者を作るのに要ります）")
        return 1
    import secrets
    合 = "Gr-" + secrets.token_urlsafe(18) + "!aZ9"
    作る = ("$pw = ConvertTo-SecureString '%s' -AsPlainText -Force; "
            "if (Get-LocalUser -Name '%s' -ErrorAction SilentlyContinue) { "
            "Set-LocalUser -Name '%s' -Password $pw } else { "
            "New-LocalUser -Name '%s' -Password $pw -AccountNeverExpires "
            "-PasswordNeverExpires -UserMayNotChangePassword | Out-Null }"
            % (合, e.利用者, e.利用者, e.利用者))
    o = e._走らす(作る)
    if o is None or o.returncode != 0:
        print("利用者を作れませんでした: %s" % ((o.stderr if o else "") or "?"))
        return 1
    os.makedirs(os.path.dirname(e.合言葉の置き場), exist_ok=True)
    with 開く(e.合言葉の置き場, "w") as f:
        f.write(合)
    # **合言葉は人だけのもの。**継承を切って、自分と管理者だけにする。
    e._icacls(e.合言葉の置き場, "/inheritance:r", "/Q")
    e._icacls(e.合言葉の置き場, "/grant", "%s:F" % (os.environ.get("USERNAME") or ""),
              "/Q")
    # **初回のログオンでプロファイルが作られる。**ここで済ませておかないと、
    # 最初の1回だけ十数秒余計にかかり、時間切れを「壁が動かない」と読む。
    t0 = time.time()
    暖機 = e._走らす(
        "$pw = ConvertTo-SecureString (Get-Content -Raw '%s').Trim() "
        "-AsPlainText -Force; "
        "$c = New-Object System.Management.Automation.PSCredential('%s',$pw); "
        "Start-Process -FilePath cmd.exe -ArgumentList '/c','ver' -Credential $c "
        "-WorkingDirectory 'C:\\Windows\\Temp' -Wait -WindowStyle Hidden"
        % (e.合言葉の置き場, e.利用者), 待ち=300)
    print("初回のログオン: %.1f 秒（%s）"
          % (time.time() - t0,
             "通った" if (暖機 and 暖機.returncode == 0) else "通らない: "
             + ((暖機.stderr if 暖機 else "") or "?").strip()[:200]))
    print("作りました: %s（合言葉は %s）" % (e.利用者, e.合言葉の置き場))
    print("SID: %s" % (e._sid() or "引けません"))
    print("使えるか: %s" % e.使えるか())
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--壁の利用者を作る":
        sys.exit(壁の利用者を作る())
    if len(sys.argv) >= 2 and sys.argv[1] == "--verify":
        e = pick_enforcer()
        m = いまの機械()
        print("機械: %s %s" % (platform.system(), platform.release()))
        print("窓口: %s" % m.name)
        for x in m.測れないもの():
            print("      × %s" % x)
        print("執行: %s（通信は%s）" % (e.name, e.通信の粒度))
        for x in 囲いの見送り():
            # **弱い壁に黙って落とさない。**立たなかった囲いがあれば、それを先に言う。
            print("      見送った囲い: %s" % x)
        print("      縛れる壁: %s" % "・".join(e.縛れる壁) if e.縛れる壁 else "      縛れる壁: なし")
        print()
        for w, (ok, why) in verify(e).items():
            print("  %s %-4s %s" % ("○" if ok else "★", w, why))
        sys.exit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "--sweep":
        # **黙って終わった走りを、外側から決着させる。**
        # 静かなときは何も言わない（毎回しゃべる知らせは読まれなくなる）が、
        # **見つけたときは必ず終了コードを変える**ので、
        # 定時実行の失敗として pc-check が拾える。
        静か = "--quiet" in sys.argv
        s = sweep(kill="--殺さない" not in sys.argv)
        if s["中断"]:
            print("黙って終わった走りが %d 件ありました" % len(s["中断"]))
            for x in s["中断"]:
                print("  ✗ %s  %s" % (x["id"], x.get("作業場")))
                for y in x.get("理由", [])[:4]:
                    print("      %s" % y)
                print("      受領証: %s" % x.get("受領証"))
        if s["期限超過"]:
            print("期限を過ぎたのに終わっていない走りが %d 件あります"
                  "（親は生きている＝壁時計か採点が固まっている）" % len(s["期限超過"]))
            for x in s["期限超過"]:
                print("  ! %s  %s 秒超過  %s" % (x["id"], x.get("超過秒"),
                                                 x.get("作業場")))
        if s["読めない予告"]:
            # **監査できないことを黙らない。**読めない予告の走りは、終わったのかも分からない。
            print("読めない予告が %d 件あります（その走りが終わったか確かめられない）"
                  % len(s["読めない予告"]))
            for d, わけ in s["読めない予告"][:10]:
                print("  ? %s  %s" % (d, わけ))
        if not 静か and not s["中断"] and not s["期限超過"] and not s["読めない予告"]:
            print("黙って終わった走りはありません"
                  "（走行中 %d 件・見た %d 件・捨てた %d 件）"
                  % (len(s["走行中"]), s["見た"], s["捨てた"]))
        sys.exit(4 if s["期限超過"] else (3 if s["中断"] else (5 if s["読めない予告"] else 0)))

    if len(sys.argv) >= 2 and sys.argv[1] == "--成績":
        # **使い込みを数で出す。**
        # 「壊れなくなった」は日数ではなく、**走った数と、赤の出かた**で見る。
        # 完成度を語るときに、印象ではなくこの表を見るためのもの。
        日数 = int(sys.argv[2]) if len(sys.argv) > 2 else 14
        境 = time.time() - 日数 * 86400
        走り = []
        for d, 約, 受 in 記録を読む():
            if not 受:
                continue
            t0 = 約.get("始めた") or 0
            if t0 < 境:
                continue
            走り.append((t0, 約, 受))
        if not 走り:
            print("直近 %d 日に終わった走りはありません" % 日数)
            sys.exit(0)
        から = time.strftime("%m-%d", time.localtime(min(x[0] for x in 走り)))
        まで = time.strftime("%m-%d", time.localtime(max(x[0] for x in 走り)))
        print("直近 %d 日（%s〜%s）の走り %d 件" % (日数, から, まで, len(走り)))
        数 = {}
        壁 = {}
        場所 = set()
        試験 = 0
        for t0, 約, 受 in 走り:
            数[受.get("判定")] = 数.get(受.get("判定"), 0) + 1
            if 受.get("壁に当たった"):
                名 = str(受["壁に当たった"]).split("（")[0][:14]
                壁[名] = 壁.get(名, 0) + 1
            w = 約.get("作業場") or ""
            場所.add(w)
            if "guardrun-verify" in w or "/private/tmp/guardrun" in w:
                試験 += 1
        print("  判定   " + " ／ ".join("%s %d" % (k, v)
                                        for k, v in sorted(数.items())))
        print("  作業場 %d か所（うち試験の作業場 %d 件）" % (len(場所), 試験))
        if 壁:
            print("  壁に当たった " + " ／ ".join("%s %d" % (k, v)
                                                  for k, v in 壁.items()))
        # **日ごとに見る。**使い続けているかは、合計ではなく並びに出る。
        日 = {}
        for t0, _約, 受 in 走り:
            k = time.strftime("%m-%d", time.localtime(t0))
            日.setdefault(k, []).append(受.get("判定"))
        print("  日ごと:")
        for k in sorted(日)[-14:]:
            v = 日[k]
            赤 = sum(1 for x in v if x in ("赤", "中断", "失敗"))
            print("    %s  %2d 件 %s%s" % (k, len(v), "●" * min(len(v), 20),
                                            ("  ✗%d" % 赤) if 赤 else ""))
        # **「壊れなくなった」の判定はここでしない。**数を出すだけ。
        # 何日続けば足りるかは人が決めること（道具が決めると自分に甘くなる）。
        sys.exit(0)

    if len(sys.argv) >= 2 and sys.argv[1] == "--runs":
        数 = {}
        触 = {"あり": 0, "なし": 0, "古い受領証": 0}
        for _d, 約, 受 in 記録を読む():
            印 = (受 or {}).get("判定") or 約.get("状態")
            数[印] = 数.get(印, 0) + 1
            t = (受 or {}).get("触った跡")
            触["古い受領証" if t is None else ("あり" if t else "なし")] += 1
            print("  %-4s %s  %s  %s" % (印, 約.get("id"),
                                         約.get("始めた時刻"), 約.get("作業場")))
        # **数えられない印は、試されていないのか出番が無いのか分からない。**
        if 数:
            print("\n  判定: " + "・".join("%s %d" % (k, v) for k, v in sorted(数.items())))
            print("  触った跡: あり %d・なし %d（記録に無い古い受領証 %d）"
                  % (触["あり"], 触["なし"], 触["古い受領証"]))
        sys.exit(0)

    引数 = sys.argv[1:]
    prove = True
    期待, 宣言者 = None, None
    while 引数 and 引数[0] in ("--証明なし", "--期待"):
        if 引数[0] == "--証明なし":
            # **証明そのものを試すとき用。**ふつうは使わない。
            prove, 引数 = False, 引数[1:]
            continue
        # **期待はコマンドからも宣言できる。**（2026-09-27）
        # 前は run(期待=...) の呼び出しにしか口が無く、コマンドで使う人（qwc の壁・
        # ⑥ の実験）は宣言しようがなかった。形式版2の受領証67件が全部「未宣言」だった。
        # ファイルは走らせる前に読んで予告に確定させる（中の命令が後から書き換えても効かない）。
        if len(引数) < 2:
            print("--期待 には JSON ファイルの場所が要ります", file=sys.stderr)
            sys.exit(2)
        try:
            with open(引数[1], encoding="utf-8") as f:
                期待 = json.load(f)
            _期待の形を確かめる(期待)
        except (OSError, ValueError) as e:
            print("期待を読めません（%s）: %s" % (引数[1], e), file=sys.stderr)
            sys.exit(2)
        宣言者 = "コマンドの --期待（%s）" % os.path.abspath(引数[1])
        引数 = 引数[2:]
    if len(引数) < 2:
        print("使い方: guardrun.py --verify | --sweep [--quiet] | --runs "
              "| [--証明なし] [--期待 <期待.json>] <作業場> <命令...>", file=sys.stderr)
        sys.exit(2)
    r = run(引数[1:], 引数[0], prove=prove, 期待=期待, 宣言者=宣言者)
    r.pop("_出力", None)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    # **失敗・拒否・赤を終了コード0で返さない。**（2026-09-24・Codex の監査）
    # 前は何が起きても 0 で、終了コードだけを見る呼び出し元には全部成功に見えた。
    # 約束は qwc と同じ: 緑・青は 0／命令が 0 以外で終わったらその値／それ以外（中断・拒否・赤）は 3。
    子 = r.get("終了コード")
    if isinstance(子, int) and 0 < 子 < 256:
        sys.exit(子)
    sys.exit(0 if r.get("判定") in ("緑", "青") else 3)
