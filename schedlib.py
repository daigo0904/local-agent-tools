#!/usr/bin/env python3
"""常駐と定時の窓口。**launchd と systemd と「仕組みの無い機械」を、同じ形で扱う。**

この家は launchd 前提で書かれていた（2026-09-23 に数えたら launchctl 60か所・plist 92か所）。
Linux では claw が半分しか動かず、Windows では起動もしなかった。**OS ごとの呼び分けを
ここ1か所に閉じ込める**ことで、点呼・見張り・claw は「仕組みの名前」を知らずに済む。

返すのは3つだけ。

    一覧()        登録されている仕事と、その契約（間隔・種類）
    帳簿(label)   本人には書けない記録（起き直しの回数・終了コード・いま走っているか）
    蹴る(label)   走っていなければ起こす（走っている相手には手を出さない）

**数えられないものは None を返す。**systemd は「何回起き直したか」を持っていないので、
`runs` は None になり、代わりに `走り出した`（最後に走り出した時刻）が入る。
0 を返すと「一度も走っていない」に化けるので、**読めないと数えられないを混ぜない。**
"""
import json
import os
import re
import subprocess
import sys
import time

接頭 = "ai.openclaw."
定時, 常駐, 期限なし, 測れず = "定時", "常駐", "期限なし", "測れない"


def _走らせる(argv, timeout=15):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def 仕組み():
    """この機械で使える仕組み。無ければ None。"""
    if sys.platform == "darwin" and _どこ("launchctl"):
        return "launchd"
    if _どこ("systemctl"):
        return "systemd"
    return None


def _どこ(名):
    import shutil
    return shutil.which(名)


# ── launchd ──────────────────────────────────────────────

def _plist(path):
    """plist を読む。読めなければ None（**空の辞書を返さない**）。"""
    import plistlib
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except (OSError, ValueError):
        return None


def _calendar_interval(spec):
    """StartCalendarInterval から、だいたいの間隔（秒）。"""
    specs = spec if isinstance(spec, list) else [spec]
    best = 86400
    for s in specs:
        if not isinstance(s, dict):
            continue
        if "Minute" in s and "Hour" not in s:
            best = min(best, 3600)
        elif "Hour" in s and "Weekday" not in s and "Day" not in s:
            best = min(best, 86400)
    if len(specs) > 1:
        best = max(60, best // len(specs))
    return best


def _launchd一覧():
    out = {}
    r = _走らせる(["launchctl", "list"])
    if r is None:
        return out
    for row in r.stdout.splitlines():
        cols = row.split("\t")
        if len(cols) != 3 or not cols[2].startswith(接頭):
            continue
        label = cols[2]
        名 = label.split(".")[-1]
        b = _launchd帳簿(label)
        path = (b or {}).get("path") or os.path.expanduser(
            "~/Library/LaunchAgents/%s.plist" % label)
        p = _plist(path)
        if p is None:
            out[label] = {"名前": 名, "種類": 測れず, "間隔": None, "元": "launchd",
                          "ログ": None, "プログラム": None, "path": path,
                          "理由": "plist が読めない（%s）" % path}
            continue
        if p.get("StartInterval"):
            種, 間 = 定時, int(p["StartInterval"])
        elif p.get("StartCalendarInterval"):
            種, 間 = 定時, _calendar_interval(p["StartCalendarInterval"])
        elif p.get("KeepAlive"):
            種, 間 = 常駐, None
        else:
            種, 間 = 期限なし, None
        prog = p.get("Program") or (p.get("ProgramArguments") or [None])[0]
        out[label] = {"名前": 名, "種類": 種, "間隔": 間, "元": "launchd",
                      "ログ": p.get("StandardOutPath"), "プログラム": prog,
                      "path": path}
    return out


def _launchd帳簿(label):
    r = _走らせる(["launchctl", "print", "gui/%d/%s" % (os.getuid(), label)])
    if r is None or r.returncode != 0:
        return None
    return _launchd帳簿を読む(r.stdout)


def _launchd帳簿を読む(text):
    """`launchctl print` の出力から記録を取る。**行の残り全部を取る**
    （`(\\S+)` だと "not running" が "not" になる）。"""
    d = {"runs": None, "exit": None, "state": None, "pid": None, "path": None,
         "走り出した": None, "回数が数えられない": False}
    for row in text.splitlines():
        row = row.strip()
        for 鍵, 型, 正 in (("path", str, r"^path = (\S.*)$"),
                          ("runs", int, r"^runs = (\d+)$"),
                          ("exit", int, r"^last exit code = (-?\d+)$"),
                          ("state", str, r"^state = (.+)$"),
                          ("pid", int, r"^pid = (\d+)$")):
            m = re.match(正, row)
            if m and d[鍵] is None:
                d[鍵] = 型(m.group(1))
    return d


# ── systemd（Linux）─────────────────────────────────────

def _systemd一覧():
    """`systemctl --user` の service と timer から契約を作る。

    **timer が付いていれば定時、Restart= が付いていれば常駐。**
    どちらも無ければ「期限なし」——launchd の plist と同じ読み方にそろえる。"""
    out = {}
    r = _走らせる(["systemctl", "--user", "list-unit-files", "--no-legend",
                 "--no-pager", "%s*" % 接頭])
    if r is None:
        return out
    units = [row.split()[0] for row in r.stdout.splitlines() if row.strip()]
    timers = {u[:-6] + ".service" for u in units if u.endswith(".timer")}
    for u in units:
        if not u.endswith(".service"):
            continue
        label = u[:-8]
        情報 = _systemd属性(u, ["FragmentPath", "Restart", "ExecStart"])
        間 = _systemd間隔(label + ".timer") if u in timers else None
        if 間 is not None:
            種 = 定時
        elif (情報.get("Restart") or "no") != "no":
            種, 間 = 常駐, None
        else:
            種, 間 = 期限なし, None
        out[label] = {"名前": label.split(".")[-1], "種類": 種, "間隔": 間,
                      "元": "systemd", "ログ": None,
                      "プログラム": (情報.get("ExecStart") or "").strip() or None,
                      "path": 情報.get("FragmentPath")}
    return out


def _systemd属性(unit, keys):
    r = _走らせる(["systemctl", "--user", "show", unit,
                 "-p", ",".join(keys), "--no-pager"])
    if r is None:
        return {}
    return _systemd属性を読む(r.stdout)


def _systemd属性を読む(text):
    出 = {}
    for row in text.splitlines():
        if "=" in row:
            k, v = row.split("=", 1)
            出[k.strip()] = v.strip()
    return 出


def _時間を秒に(値):
    """systemd の時間の書き方を秒にする。

    **数字だけを拾ってはいけない。**`OnUnitActiveUSec=1d` の "1" を拾って
    「1秒ごと」と読んでいた（2026-09-23、Linux の実物で発覚）。
    マイクロ秒の整数（86400000000）と、`1d` `30s` `5min 20s` の両方を読む。"""
    値 = (値 or "").strip()
    if not 値:
        return None
    if 値.isdigit():                      # マイクロ秒
        return max(1, int(値) // 1_000_000)
    単位 = {"usec": 1e-6, "us": 1e-6, "ms": 1e-3, "msec": 1e-3, "s": 1, "sec": 1,
           "second": 1, "seconds": 1, "m": 60, "min": 60, "minute": 60,
           "minutes": 60, "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
           "d": 86400, "day": 86400, "days": 86400, "w": 604800, "week": 604800}
    合計 = 0.0
    見つけた = False
    for 数, 単 in re.findall(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", 値):
        if 単 in 単位:
            合計 += float(数) * 単位[単]
            見つけた = True
    return max(1, int(合計)) if 見つけた else None


def _systemd間隔(timer):
    """timer の間隔（秒）。OnUnitActiveSec / OnCalendar から。読めなければ None。"""
    d = _systemd属性(timer, ["TimersMonotonic", "TimersCalendar"])
    m = re.search(r"OnUnitActiveUSec=([^;}\s]+)", d.get("TimersMonotonic") or "")
    if m:
        秒 = _時間を秒に(m.group(1))
        if 秒:
            return 秒
    if d.get("TimersCalendar"):
        cal = d["TimersCalendar"]
        if "*-*-* *:*:00" in cal or "minutely" in cal:
            return 60
        if re.search(r"\*:0?0/(\d+)", cal):
            return int(re.search(r"\*:0?0/(\d+)", cal).group(1)) * 60
        if "hourly" in cal or re.search(r"\*-\*-\* \*:00:00", cal):
            return 3600
        return 86400
    return None


def _systemd帳簿(label):
    d = _systemd属性(label + ".service",
                    ["NRestarts", "ExecMainStatus", "ActiveState", "SubState",
                     "MainPID", "FragmentPath", "ExecMainStartTimestampMonotonic",
                     "ExecMainStartTimestamp"])
    if not d:
        return None
    return _systemd帳簿を読む(d)


def _systemd帳簿を読む(d):
    """**systemd は「何回走ったか」を持っていない。**NRestarts は落ちて起き直した
    回数で、定時に呼ばれた回数ではない。数えられないものを数えたふりをしないため、
    `runs` は None にして、代わりに最後に走り出した時刻を返す。"""
    走 = None
    ts = d.get("ExecMainStartTimestampMonotonic")
    if ts and ts.isdigit() and int(ts) > 0:
        走 = time.time() - (time.clock_gettime(time.CLOCK_MONOTONIC)
                           - int(ts) / 1_000_000.0)
    pid = d.get("MainPID")
    状態 = d.get("SubState") or d.get("ActiveState")
    return {"runs": None, "回数が数えられない": True, "走り出した": 走,
            "exit": int(d["ExecMainStatus"]) if (d.get("ExecMainStatus") or "").lstrip("-").isdigit() else None,
            "state": "running" if 状態 == "running" else "not running",
            "pid": int(pid) if (pid or "0").isdigit() and int(pid) else None,
            "path": d.get("FragmentPath")}


# ── 窓口 ────────────────────────────────────────────────

def 一覧():
    """登録されている仕事と契約。**この機械に仕組みが無ければ空。**"""
    s = 仕組み()
    if s == "launchd":
        return _launchd一覧()
    if s == "systemd":
        return _systemd一覧()
    return {}


def 帳簿(label):
    """本人には書けない記録。読めなければ None。"""
    s = 仕組み()
    if s == "launchd":
        return _launchd帳簿(label)
    if s == "systemd":
        return _systemd帳簿(label)
    return None


def PID一覧(接頭=接頭):
    """登録されている仕事と、その PID（走っていなければ None）。

    **この家のものだけに絞らない呼び方もできる**（ollama のように別の名前で
    登録されているものを見るため）。接頭=None で全部。"""
    出 = {}
    s = 仕組み()
    if s == "launchd":
        r = _走らせる(["launchctl", "list"])
        if r is None:
            return 出
        for row in r.stdout.splitlines():
            cols = row.split("\t")
            if len(cols) != 3:
                continue
            label = cols[2]
            if 接頭 and not label.startswith(接頭):
                continue
            出[label] = int(cols[0]) if cols[0].lstrip("-").isdigit() and cols[0] != "-" else None
    elif s == "systemd":
        r = _走らせる(["systemctl", "--user", "list-units", "--type=service",
                     "--all", "--no-legend", "--no-pager",
                     ("%s*" % 接頭) if 接頭 else "*"])
        if r is None:
            return 出
        for row in r.stdout.splitlines():
            名 = row.split()[0] if row.split() else ""
            if not 名.endswith(".service"):
                continue
            label = 名[:-8]
            b = _systemd帳簿(label)
            出[label] = (b or {}).get("pid")
    return 出


def 外す(label):
    """登録から外す（手入れの間だけ止めるときに使う）。(できたか, 説明)。"""
    s = 仕組み()
    if s == "launchd":
        r = _走らせる(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), label)],
                    timeout=30)
        return (r is not None and r.returncode in (0, 3)), \
               ((r.stderr or r.stdout).strip()[:120] if r else "launchctl が動かない")
    if s == "systemd":
        r = _走らせる(["systemctl", "--user", "stop", label + ".service"], timeout=30)
        return (r is not None and r.returncode == 0), \
               ((r.stderr or "").strip()[:120] if r else "systemctl が動かない")
    return False, "この機械には常駐・定時の仕組みが無い"


def 入れる(label, path=None):
    """登録に戻す（外したものを元へ）。(できたか, 説明)。"""
    s = 仕組み()
    if s == "launchd":
        plist = path or os.path.expanduser("~/Library/LaunchAgents/%s.plist" % label)
        r = _走らせる(["launchctl", "bootstrap", "gui/%d" % os.getuid(), plist],
                    timeout=30)
        return (r is not None and r.returncode == 0), \
               ((r.stderr or "").strip()[:120] if r else "launchctl が動かない")
    if s == "systemd":
        r = _走らせる(["systemctl", "--user", "start", label + ".service"], timeout=30)
        return (r is not None and r.returncode == 0), \
               ((r.stderr or "").strip()[:120] if r else "systemctl が動かない")
    return False, "この機械には常駐・定時の仕組みが無い"


def 蹴る(label, 殺す=False, 走っていれば見送る=False, path=None):
    """起こす。**ここは OS への頼み方だけ**——「走っている相手は蹴らない」「短い間に
    何度も蹴らない」といった方針は、呼ぶ側（guardlib）が持つ。

    返り値は (どうしたか, 説明)。どうしたか = kicked / running / failed / 仕組みなし。
    外れていたら読み込み直す（launchd は bootstrap、systemd は daemon-reload + enable）。"""
    s = 仕組み()
    if 走っていれば見送る:
        b = 帳簿(label)
        if b and (b.get("state") == "running" or b.get("pid")):
            return "running", "走っているので手を出さない"
    if s == "launchd":
        cmd = ["launchctl", "kickstart"] + (["-k"] if 殺す else []) + \
              ["gui/%d/%s" % (os.getuid(), label)]
        r = _走らせる(cmd, timeout=30)
        if r is not None and r.returncode == 0:
            return "kicked", ("殺してから起こした" if 殺す else "蹴った")
        plist = path or os.path.expanduser(
            "~/Library/LaunchAgents/%s.plist" % label)
        if not os.path.exists(plist):
            return "failed", "plist が無い"
        b2 = _走らせる(["launchctl", "bootstrap", "gui/%d" % os.getuid(), plist],
                     timeout=30)
        if b2 is not None and b2.returncode == 0:
            return "kicked", "外れていたので読み込み直した"
        理由 = ((b2.stderr if b2 else "") or (r.stderr if r else "")
               or "理由不明").strip().splitlines()
        return "failed", (理由[0][:120] if 理由 else "理由不明")
    if s == "systemd":
        # systemd の restart は走っていても入れ直す（launchd の -k と同じ）
        r = _走らせる(["systemctl", "--user", "restart", label + ".service"],
                    timeout=30)
        if r is not None and r.returncode == 0:
            return "kicked", "systemctl restart で起こした"
        _走らせる(["systemctl", "--user", "daemon-reload"], timeout=30)
        r2 = _走らせる(["systemctl", "--user", "enable", "--now",
                      label + ".service"], timeout=30)
        if r2 is not None and r2.returncode == 0:
            return "kicked", "外れていたので enable --now で入れ直した"
        return "failed", ((r2.stderr if r2 else "") or (r.stderr if r else "")
                          or "systemctl が動かない").strip()[:120]
    return "仕組みなし", "この機械には常駐・定時の仕組みが無い"


# ── 使い捨ての仕事（証明で使う）────────────────────────────

def 使い捨て登録(label, sh, 間隔=86400, plist置き場=None):
    """**証明のために、本物の OS に使い捨ての仕事を登録する。**

    走らせるのはこちらから1回ずつ（間隔を長くしておく）。
    登録できなければ False——**そのときは「測れない」と言うこと。**"""
    s = 仕組み()
    if s == "launchd":
        import plistlib
        path = plist置き場 or os.path.expanduser("~/.%s.plist" % label)
        try:
            with open(path, "wb") as f:
                plistlib.dump({"Label": label,
                               "ProgramArguments": ["/bin/sh", "-c", sh],
                               "RunAtLoad": False,
                               "StartInterval": 間隔}, f)
        except OSError:
            return False
        _走らせる(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), label)])
        r = _走らせる(["launchctl", "bootstrap", "gui/%d" % os.getuid(), path])
        return r is not None and r.returncode == 0
    if s == "systemd":
        d = os.path.expanduser("~/.config/systemd/user")
        try:
            os.makedirs(d, exist_ok=True)
            # **中身はファイルに出す。**unit の ExecStart は1行しか書けないので、
            # 複数行のシェルをそのまま入れると unit が壊れて登録だけ残る
            # （2026-09-23、Linux の実物でそうなった。台帳には載るのに記録が読めない）。
            本体 = os.path.join(d, label + ".sh")
            with open(本体, "w") as f:
                f.write("#!/bin/sh\n" + sh + "\n")
            os.chmod(本体, 0o755)
            with open(os.path.join(d, label + ".service"), "w") as f:
                f.write("[Unit]\nDescription=%s\n[Service]\nType=oneshot\n"
                        "ExecStart=/bin/sh %s\n" % (label, 本体))
            # **timer を付けるのは「定時の契約」を持たせるため。**
            # 無いと期限の無い仕事に見えて、証明が見たい形にならない。
            with open(os.path.join(d, label + ".timer"), "w") as f:
                f.write("[Unit]\nDescription=%s timer\n[Timer]\n"
                        "OnUnitActiveSec=%d\n[Install]\nWantedBy=timers.target\n"
                        % (label, 間隔))
        except OSError:
            return False
        r = _走らせる(["systemctl", "--user", "daemon-reload"], timeout=30)
        if r is None or r.returncode != 0:
            return False
        _走らせる(["systemctl", "--user", "start", label + ".timer"], timeout=30)
        return True
    return False


def _sh引用(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def 使い捨て削除(label, plist置き場=None):
    s = 仕組み()
    if s == "launchd":
        _走らせる(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), label)])
        try:
            os.unlink(plist置き場 or os.path.expanduser("~/.%s.plist" % label))
        except OSError:
            pass
        return True
    if s == "systemd":
        _走らせる(["systemctl", "--user", "stop", label + ".timer"], timeout=30)
        _走らせる(["systemctl", "--user", "stop", label + ".service"], timeout=30)
        d = os.path.expanduser("~/.config/systemd/user")
        for 名 in (label + ".service", label + ".timer", label + ".sh"):
            try:
                os.unlink(os.path.join(d, 名))
            except OSError:
                pass
        _走らせる(["systemctl", "--user", "daemon-reload"], timeout=30)
        return True
    return False


def 一度走らせる(label):
    """使い捨ての仕事を1回だけ走らせる。**終わるまで待つかどうかは仕組みによる**
    （systemd の oneshot は start が終わるまで返らない。launchd は返ってくるので、
    呼んだ側が帳簿で待つ）。"""
    s = 仕組み()
    if s == "launchd":
        r = _走らせる(["launchctl", "kickstart",
                     "gui/%d/%s" % (os.getuid(), label)], timeout=30)
        return r is not None and r.returncode == 0
    if s == "systemd":
        r = _走らせる(["systemctl", "--user", "start", label + ".service"],
                    timeout=60)
        # oneshot が 0 以外で終わると start も 0 以外を返す。**それは失敗ではなく結果。**
        return r is not None
    return False


# ── 自己検査 ─────────────────────────────────────────────

def selftest():
    """**読み取りの形だけは、どの OS でも試せる。**実物の出力を写した見本で当てる。
    実物に当たるのは、その仕組みがある機械にいるときだけ。"""
    ok = []
    見本 = """	path = /Users/x/Library/LaunchAgents/ai.openclaw.watchdog.plist
	state = not running
	runs = 3279
	last exit code = 1
"""
    d = _launchd帳簿を読む(見本)
    ok.append(("launchd の記録を読む",
               d["runs"] == 3279 and d["exit"] == 1 and d["state"] == "not running"
               and d["path"].endswith("watchdog.plist") and d["pid"] is None))
    ok.append(("「not running」を途中で切らない", d["state"] == "not running"))

    ok.append(("systemd の時間を読む（数字だけ拾わない）",
               _時間を秒に("86400000000") == 86400 and _時間を秒に("1d") == 86400
               and _時間を秒に("30s") == 30 and _時間を秒に("5min") == 300
               and _時間を秒に("") is None))
    見本2 = {"NRestarts": "0", "ExecMainStatus": "1", "ActiveState": "active",
            "SubState": "running", "MainPID": "1234",
            "FragmentPath": "/home/x/.config/systemd/user/ai.openclaw.watchdog.service",
            "ExecMainStartTimestampMonotonic": "0"}
    s2 = _systemd帳簿を読む(見本2)
    ok.append(("systemd の記録を読む",
               s2["runs"] is None and s2["回数が数えられない"] is True
               and s2["exit"] == 1 and s2["state"] == "running" and s2["pid"] == 1234))
    ok.append(("数えられないものを 0 にしない", s2["runs"] is None))
    属 = _systemd属性を読む("NRestarts=2\nActiveState=active\n")
    ok.append(("systemd の属性を読む", 属 == {"NRestarts": "2", "ActiveState": "active"}))

    s = 仕組み()
    ok.append(("この機械の仕組みを言える", s in ("launchd", "systemd", None)))
    if s:
        c = 一覧()
        ok.append(("実物の台帳が読める（%s・%d本）" % (s, len(c)), isinstance(c, dict)))
        if c:
            label = sorted(c)[0]
            b = 帳簿(label)
            ok.append(("実物の記録が読める（%s）" % label,
                       b is None or ("state" in b and ("runs" in b))))
    else:
        ok.append(("仕組みが無いときは空を返す", 一覧() == {} and 帳簿("x") is None))

    for 名, v in ok:
        print(("  ok  " if v else "  NG  ") + 名)
    print("\n  %d / %d 件\n" % (sum(1 for _, v in ok if v), len(ok)))
    return 0 if all(v for _, v in ok) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--list" in sys.argv:
        print(json.dumps(一覧(), ensure_ascii=False, indent=1))
        sys.exit(0)
    print("使い方: schedlib.py --selftest | --list", file=sys.stderr)
    sys.exit(2)
