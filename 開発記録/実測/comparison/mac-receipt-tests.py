#!/usr/bin/env python3
"""guardrun-印の試験 — 受領証の印が、走りの本当の終わり方と合っているか。

    guardrun-印の試験 [guardrun.py の場所]     結果を1行ずつと、最後に JSON を1行出す

**「黙る失敗を無害な印で残さない」を、壊れ方ごとに実走で確かめる。**
2026-09-23、この一式は scratchpad の使い捨てスクリプトでしか回っていなかった。
直した穴（見届け役の偽造・FIFO で固まる・壁が立たないのに青…）は、
次に誰かが guardrun を触って戻しても、気づく仕組みが無かった。

中身は3つ。
    ふつう     何もしない=青・書く=緑・exit≠0=失敗・シグナル=中断・無い命令=失敗
    書いて失敗  差分があっても exit≠0 は緑にしない（2026-09-24・本人の決定）
    壊し       中の命令が見届けの記録を偽造・消去・FIFO・リンクにする／見届け役を殺す
    壁が立たない 壁の起動役を「警告を言って落ちる偽物」に差し替える（対話あり・なし）

**壁の証明は取らない（prove=False）・受領証は使い捨ての置き場に書く。**
本物の受領証（--成績 の数）と証明の控えを汚さないため。
固まる退行（FIFO）もあり得るので、呼ぶ側は時間切れを付けること（guard-drill は付けている）。
"""
import json
import os
import shutil
import signal
import sys
import tempfile
import importlib.machinery
import importlib.util

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/bin/guardrun.py")
spec = importlib.util.spec_from_loader(
    "guardrun_印の試験", importlib.machinery.SourceFileLoader("guardrun_印の試験", PATH))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

PY = sys.executable
T = "p=os.environ['TMPDIR']+'/見届け.txt';"
窓 = os.name == "nt"
ABRT = int(getattr(signal, "SIGABRT", 6))

# (名, 命令の中身, 期待する印, 許す終了コード or None)。中身が None なら「無い命令」を走らせる
ケース = [
    ("何もしない",          "pass",                                         "青",  (0,)),
    ("書く",               "open('a','w').write('x')",                     "緑",  (0,)),
    ("dist に残す", "import os;os.mkdir('dist');open('dist/result.txt','w').write('remaining')", "青", (0,)),
    ("書いて消す", "import os;open('a','w').write('x');os.unlink('a')", "青", (0,)),
    ("exit 3",            "import sys;sys.exit(3)",                        "失敗", (3,)),
    ("自分で exit 130",     "import sys;sys.exit(130)",                      "失敗", (130,)),
    ("自分で exit 153",     "import sys;sys.exit(153)",                      "失敗", (153,)),
    ("中身が壁の名を言う",   "print('sandbox-exec: x');print('bwrap: x');import sys;sys.exit(3)",
                                                                           "失敗", (3,)),
    ("書いて exit 3",       "import sys;open('a','w').write('x');sys.exit(3)", "失敗", (3,)),
    ("記録を消して成功",     "import os;%s os.unlink(p)" % T,                  "青",  (0,)),
    ("無い命令",            None,                                           "失敗", None),
    # 壁時計で止めた走りは、書いていても緑にせず青・「時間切れで止めた」と書く（2026-09-24・母艦の決定）
    ("書いて眠り続ける（壁時計）", "import time;open('a','w').write('x');time.sleep(60)", "青", None),
]
壁時計のケース = {"書いて眠り続ける（壁時計）": 3}
if not 窓:
    # 量の上限は guardrun 自身が rlimit で掛ける（Windows には rlimit が無い＝★ と申告済み）。
    # **Windows で書けてしまうのは試験の期待のほうが違う**（2026-09-24、GitHub で 緑・終了 0）。
    ケース += [("上限まで書いて EFBIG", "open('big','wb').write(b'x'*200000)", "失敗", None)]
    ケース += [
        ("SIGABRT で落ちる",  "import os;os.abort()",                         "中断", (-ABRT, 128 + ABRT)),
        ("書いて SIGABRT",   "import os;open('a','w').write('x');os.abort()", "中断", (-ABRT, 128 + ABRT)),
        ("自分を SIGKILL",   "import os;os.kill(os.getpid(),9)",              "中断", (-9, 137)),
        ("偽造して見届け役を殺す",
         "import os;%s open(p,'w').write('起動\\n終了 0\\n');os.kill(os.getppid(),9);os._exit(3)" % T,
                                                                             "中断", None),
        ("書いて記録を消し見届け役を殺す",
         "import os;%s open('a','w').write('x');os.unlink(p);os.kill(os.getppid(),9)" % T,
                                                                             "中断", None),
        # 偽の「CPU の上限で止まった」を書いて見届け役を殺す。記録だけで「壁に当たった」と読むと、
        # 突き合わせまで飛ばされて青になった（2026-09-24・Codex の指摘・80c2abb が作った穴）。
        ("偽の上限を書いて見届け役を殺す",
         "import os,signal;%s open(p,'w').write('起動\\n終了 -%%d\\n' %% signal.SIGXCPU);os.kill(os.getppid(),9)" % T,
                                                                             "中断", None),
        # 2026-09-24 Codex の監査で出た穴（印の試験で常設にする）
        ("作業場に FIFO を残す",
         "import os;os.mkfifo('trap')",                                     "緑", (0,)),
        ("git の仕掛けをリンクで置く",
         "import os;open('h.sh','w').write('#!/bin/sh\\n');os.chmod('h.sh',0o755);"
         "os.makedirs('.git/hooks',exist_ok=True);os.symlink('../../h.sh','.git/hooks/pre-commit')",
                                                                             "赤", None),
        # 対照: 本当に上限まで回った走りは、今までどおり「CPU の上限」（直しすぎていないこと）
        ("本当に CPU を使い切る",  "\nwhile True: pass",                          "青",  None),
        ("自分に SIGXCPU を送る",
         "import os,signal;os.kill(os.getpid(),signal.SIGXCPU)",           "中断", None),
        ("自分に SIGXFSZ を送る",
         "import os,signal;signal.signal(signal.SIGXFSZ,signal.SIG_DFL);os.kill(os.getpid(),signal.SIGXFSZ)",
                                                                             "中断", None),
        ("読めないフォルダに書く",
         "import os;os.makedirs('秘',exist_ok=True);open('秘/a','w').write('x'*100);os.chmod('秘',0o700)",
                                                                             "緑", (0,)),
        ("記録を FIFO にする", "import os;%s os.unlink(p);os.mkfifo(p)" % T,  "中断", None),
        ("記録をリンクにする",  "import os;%s os.unlink(p);os.symlink('/etc/hosts',p)" % T,
                                                                             "中断", None),
    ]
# **記録を狙う攻撃。**Linux で見届け役が命令に Landlock を掛けた走りでは、攻撃そのものを
# カーネルが断る（2026-09-24・母艦・未踏③）。そのときの正しい姿は「攻撃が断られて命令が
# 例外で終わる＝失敗・終了1」で、**しかも見届けの記録が無傷で本当の終了コードと合う**こと。
# 期待を緩めたぶん、記録が無傷かどうかを足して確かめる（中断で見抜く代わりに、壊されていないことを見る）。
記録を狙う = {"記録を消して成功", "偽造して見届け役を殺す", "書いて記録を消し見届け役を殺す",
              "偽の上限を書いて見届け役を殺す", "記録を FIFO にする", "記録をリンクにする"}


def 閉じ込めた(r):
    return str((r.get("見届け") or {}).get("閉じ込め") or "").startswith(("landlock", "seatbelt child separation"))


# 壁の起動役を、名乗り方の違う「立たない壁」に差し替える
偽の壁 = [
    ("警告のあと壁が立たない", 'echo "sudo: unable to resolve host x" >&2; '
                              'echo "bwrap: Creating new namespace failed" >&2; exit 1'),
    ("sudo の段で落ちる",     'echo "sudo: a password is required" >&2; exit 1'),
    ("何も言わずに落ちる",     "exit 1"),
]


def 作業場():
    親 = "/Users/Shared" if os.path.isdir("/Users/Shared") else None
    return tempfile.mkdtemp(prefix="印の試験-", dir=親)


def 片付け(d):
    shutil.rmtree(d, ignore_errors=True)
    if os.path.exists(d) and shutil.which("sudo"):
        # 別 uid が作ったものは本人にしか消せない
        import subprocess
        利用者 = os.environ.get("GUARDRUN_USER", "_guardrun")
        subprocess.run(["sudo", "-n", "-u", 利用者, "/bin/rm", "-rf", d], capture_output=True)
        shutil.rmtree(d, ignore_errors=True)


def 言う(x):
    """**1件ごとにすぐ出す。**固まる退行（FIFO）で時間切れになると、
    最後にまとめて出す作りでは、それまでの結果まで全部消える（2026-09-24 に踏んだ）。"""
    名, 期待, 実, 終了, ok = x
    print("%s %-24s 期待=%-3s 実際=%-4s 終了=%s" % ("○" if ok else "✗", 名, 期待, 実, 終了), flush=True)


def main():
    記録 = tempfile.mkdtemp(prefix="印の試験-記録-")
    結果 = []
    try:
        for 名, 中身, 期待, 終了 in ケース:
            if 名 in os.environ.get("印の試験_飛ばす", "").split(","):
                continue
            w = 作業場()
            try:
                argv = [PY, "-c", 中身] if 中身 is not None else [os.path.join(w, "無い命令-xyz")]
                r = g.run(argv, w, prove=False, 記録=記録, wall_sec=壁時計のケース.get(名, 30),
                          max_file_bytes=65536, **({"cpu_sec": 2} if 名 == "本当に CPU を使い切る" else {}))
                if 名 in 記録を狙う and 閉じ込めた(r):
                    期待 = "失敗（カーネルが断る）"
                    見 = r.get("見届け") or {}
                    ok = (r["判定"] == "失敗" and r["終了コード"] == 1
                          # 終わりの3つ目以降（使った CPU 時間など）は比べない
                          and 見.get("起動") is True and (見.get("終わり") or [])[:2] == ["終了", 1])
                else:
                    ok = r["判定"] == 期待 and (終了 is None or r["終了コード"] in 終了)
                if 名 == "本当に CPU を使い切る":
                    ok = ok and "CPU" in str(r.get("壁に当たった") or "")
                if 名 in 壁時計のケース:
                    ok = ok and any("時間切れで止めた" in x for x in r["理由"])
                if 名 == "自分で exit 153" and r.get("壁に当たった"):
                    ok = False
                if 名 in ("dist に残す", "書いて消す"):
                    理由 = " ".join(r["理由"])
                    ok = (ok and r.get("触った跡") is True
                          and "更新の跡はある" in 理由 and "未判定" in 理由
                          and "書いたのに残っていない" not in 理由)
                    if 名 == "dist に残す":
                        ok = ok and os.path.isfile(os.path.join(w, "dist", "result.txt"))
                結果.append((名, 期待, r["判定"], r["終了コード"], ok))
                言う(結果[-1])
            except Exception as e:                       # noqa: BLE001
                結果.append((名, 期待, "例外 %s: %s" % (type(e).__name__, e), None, False))
                言う(結果[-1])
            finally:
                片付け(w)
        # 受領証が書けない（容量切れ・権限）走りは、緑でなく中断（2026-09-24・Codex の監査 C12）
        w = 作業場()
        本物の書き = g._確定書き
        def 書けない(path, obj):
            if path.endswith("受領証.json"):
                raise OSError(28, "No space left on device")
            return 本物の書き(path, obj)
        try:
            g._確定書き = 書けない
            r = g.run([PY, "-c", "open('a','w').write('x')"], w, prove=False, 記録=記録, wall_sec=30)
            結果.append(("受領証が書けない", "中断", r["判定"], r["終了コード"],
                         r["判定"] == "中断" and r.get("受領証") is None))
        except Exception as e:                           # noqa: BLE001
            結果.append(("受領証が書けない", "中断", "例外 %s" % e, None, False))
        finally:
            g._確定書き = 本物の書き
            言う(結果[-1])
            片付け(w)
        # 親を SIGKILL された走りの作業場に、壁の利用者の ACL を残さない（2026-09-24・M6）。
        # 何を開けたかは親の記憶にしか無く、sweep が決着させたあとも残っていた。
        if not 窓 and shutil.which("sudo"):
            import subprocess, time as _t
            利用者 = os.environ.get("GUARDRUN_USER", "_guardrun")

            def ACLの数(d):
                if sys.platform == "darwin":
                    return subprocess.run(["/bin/ls", "-led", d], capture_output=True, text=True).stdout.count(利用者)
                return subprocess.run(["getfacl", "-p", d], capture_output=True, text=True).stdout.count("user:" + 利用者)
            w = 作業場()
            黙根 = tempfile.mkdtemp(prefix="印の試験-黙-")
            try:
                子 = subprocess.Popen([PY, PATH, "--証明なし", w, "sleep", "30"],
                                      env=dict(os.environ, GUARDRUN_RECORDS=黙根),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(150):
                    if any(約.get("状態") == "走行中" for _d, 約, _r in g.記録を読む(黙根)):
                        break
                    _t.sleep(0.2)
                _t.sleep(1)
                開けた数 = ACLの数(w)
                子.kill(); 子.wait()
                g.sweep(黙根, kill=True)
                残 = ACLの数(w)
                結果.append(("殺された走りの ACL", "0", "%d（開けたのは %d）" % (残, 開けた数), None,
                             残 == 0))
            except Exception as ex:                      # noqa: BLE001
                結果.append(("殺された走りの ACL", "0", "例外 %s" % ex, None, False))
            finally:
                subprocess.run(["sudo", "-n", "-u", 利用者, "pkill", "-9", "-f", "sleep 30"], capture_output=True)
                言う(結果[-1])
                片付け(w)
                shutil.rmtree(黙根, ignore_errors=True)
        # 掴んでいる場所を見られない置き去りを黙って飛ばさない（2026-09-24・M4）
        本物の窓口 = g.いまの機械

        class _見えない窓口:
            name = "試験（cwd が読めない）"

            def cwd表(self):
                return {}

            def プロセス表(self):
                return [{"pid": 4242, "ppid": 1, "pgid": 4242, "状態": "S", "経過": 3.0, "命令": "置き去り"}]
        try:
            g.いまの機械 = lambda: _見えない窓口()
            import time as _t
            _出, 探せない = g._居座り("/tmp", _t.time() - 10)
            結果.append(("掴みを見られない置き去り", "探せない", "言った" if 探せない else "黙った", None,
                         bool(探せない)))
        except Exception as ex:                          # noqa: BLE001
            結果.append(("掴みを見られない置き去り", "探せない", "例外 %s" % ex, None, False))
        finally:
            g.いまの機械 = 本物の窓口
            言う(結果[-1])
        # 殺す手が全部効かない（sudo が断る機械など）と、生きたまま「時間切れで止めた」と
        # 書いていた（2026-09-24・Codex の監査 M3）。止まらなかったと言えること。
        if not 窓:
            w = 作業場()
            印 = "止まらない命令-%d" % os.getpid()
            本物の組 = g._組ごと殺す
            本物の子孫 = g._子孫
            try:
                g._組ごと殺す = lambda pid, 組そのもの=False: False
                g._子孫 = lambda pid: []
                e = g.pick_enforcer()
                for x in (e, getattr(e, "外", None), getattr(e, "内", None)):
                    if x is not None:
                        x.皆殺し = lambda: False
                r = g.run([PY, "-c", "import time,sys;sys.argv.append(%r);time.sleep(40)" % 印], w,
                          prove=False, 記録=記録, wall_sec=3, enforcer=e, 居座りも始末=False)
                結果.append(("止められない命令", "中断", r["判定"], r["終了コード"],
                             r["判定"] == "中断" and r["終了コード"] is None
                             and any("止まらなかった" in x for x in r["理由"])))
            except Exception as ex:                      # noqa: BLE001
                結果.append(("止められない命令", "中断", "例外 %s" % ex, None, False))
            finally:
                g._組ごと殺す, g._子孫 = 本物の組, 本物の子孫
                import subprocess
                for 人 in ([], ["sudo", "-n", "-u", os.environ.get("GUARDRUN_USER", "_guardrun")]):
                    subprocess.run(人 + ["pkill", "-9", "-f", 印], capture_output=True)
                言う(結果[-1])
                片付け(w)
        if not 窓:
            for 対話 in (False, True):
                for 名, 台本 in 偽の壁:
                    w = 作業場()
                    try:
                        e = g.pick_enforcer()
                        本物 = e.囲う
                        e.囲う = (lambda 台本, 本物: (lambda argv, c, t:
                                  ["sh", "-c", 台本, "偽の壁"] + list(本物(argv, c, t))))(台本, 本物)
                        r = g.run([PY, "-c", "open('a','w').write('x')"], w, prove=False,
                                  記録=記録, wall_sec=30, enforcer=e, 対話=対話)
                        結果.append(("%s（対話%s）" % (名, "あり" if 対話 else "なし"),
                                     "拒否", r["判定"], r["終了コード"], r["判定"] == "拒否"))
                        言う(結果[-1])
                    except Exception as ex:              # noqa: BLE001
                        結果.append((名, "拒否", "例外 %s: %s" % (type(ex).__name__, ex), None, False))
                        言う(結果[-1])
                    finally:
                        片付け(w)
    finally:
        shutil.rmtree(記録, ignore_errors=True)
    print(json.dumps({"通った": sum(1 for x in 結果 if x[4]), "全部": len(結果),
                      "落ちた": [x[0] for x in 結果 if not x[4]]}, ensure_ascii=False))
    return 0 if all(x[4] for x in 結果) else 1


if __name__ == "__main__":
    sys.exit(main())
