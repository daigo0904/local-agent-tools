#!/usr/bin/env python3
"""landlock_mitodoke.py — 終了証拠の書き手を、実行対象からカーネルで切り離す試作（未踏③）

    python3 landlock_mitodoke.py            攻撃5種を Landlock なし／ありで走らせて比べる
    python3 landlock_mitodoke.py --回数 100  上乗せ時間も測る

**何を確かめるか**
guardrun の見届け役は、命令と同じ権限で「終了の証拠」（見届け.txt）を書く。
だから命令は証拠を偽造・消去・差し替え・切り詰めでき、見届け役そのものを殺せる。
今はそれを「外から見た終了コードとの突き合わせ」で後から見抜いている（ユーザ空間）。

ここでは Linux の Landlock（特権なしで使えるカーネルの LSM）で、**命令の側だけ**に
    - 作業場の外への書き込み系の操作（書く・消す・作る・名前を変える・切り詰める）を禁止
    - 自分のドメインの外のプロセスへのシグナルを禁止（ABI 6 の scoped）
を掛け、見届け役は掛けないまま証拠を書く。**断るのはカーネルで、その場で。**

採点: 攻撃ごとに、証拠が本物の終了コードと一致し、見届け役が生きて最後まで書けたか。
"""
import ctypes
import json
import os
import signal
import statistics
import sys
import tempfile
import time

# ── Landlock（linux/landlock.h）──
SYS_create, SYS_add, SYS_restrict = 444, 445, 446      # 全アーキテクチャ共通の番号
PR_SET_NO_NEW_PRIVS = 38
RULE_PATH_BENEATH = 1
F = dict(EXECUTE=1 << 0, WRITE_FILE=1 << 1, READ_FILE=1 << 2, READ_DIR=1 << 3,
         REMOVE_DIR=1 << 4, REMOVE_FILE=1 << 5, MAKE_CHAR=1 << 6, MAKE_DIR=1 << 7,
         MAKE_REG=1 << 8, MAKE_SOCK=1 << 9, MAKE_FIFO=1 << 10, MAKE_BLOCK=1 << 11,
         MAKE_SYM=1 << 12, REFER=1 << 13, TRUNCATE=1 << 14)
SCOPE_ABSTRACT_UNIX_SOCKET, SCOPE_SIGNAL = 1 << 0, 1 << 1

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64),
                ("handled_access_net", ctypes.c_uint64),
                ("scoped", ctypes.c_uint64)]


class PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def abi():
    r = libc.syscall(SYS_create, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
    return r if r >= 0 else -ctypes.get_errno()


def 書き込み系(版):
    m = (F["WRITE_FILE"] | F["REMOVE_DIR"] | F["REMOVE_FILE"] | F["MAKE_CHAR"] | F["MAKE_DIR"]
         | F["MAKE_REG"] | F["MAKE_SOCK"] | F["MAKE_FIFO"] | F["MAKE_BLOCK"] | F["MAKE_SYM"])
    if 版 >= 2:
        m |= F["REFER"]
    if 版 >= 3:
        m |= F["TRUNCATE"]
    return m


def 閉じ込める(作業場, 版):
    """呼んだプロセス（と以後の子）に Landlock を掛ける。戻れない。"""
    扱う = 書き込み系(版)
    attr = RulesetAttr(扱う, 0, (SCOPE_SIGNAL | SCOPE_ABSTRACT_UNIX_SOCKET) if 版 >= 6 else 0)
    大きさ = ctypes.sizeof(RulesetAttr) if 版 >= 6 else 16 if 版 >= 4 else 8
    fd = libc.syscall(SYS_create, ctypes.byref(attr), ctypes.c_size_t(大きさ), ctypes.c_uint32(0))
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    for 先, 許す in ((作業場, 扱う), ("/dev/null", F["WRITE_FILE"])):
        pfd = os.open(先, os.O_PATH | os.O_CLOEXEC)
        rule = PathBeneath(許す & 扱う if 先 != "/dev/null" else F["WRITE_FILE"], pfd)
        if libc.syscall(SYS_add, ctypes.c_int(fd), ctypes.c_int(RULE_PATH_BENEATH),
                        ctypes.byref(rule), ctypes.c_uint32(0)) < 0:
            raise OSError(ctypes.get_errno(), "landlock_add_rule %s" % 先)
        os.close(pfd)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl")
    if libc.syscall(SYS_restrict, ctypes.c_int(fd), ctypes.c_uint32(0)) < 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    os.close(fd)


def 見届けて走らせる(argv, 作業場, 証拠, 掛ける, 版):
    """見届け役。証拠に「起動」を書き、子を走らせ、終わりを書く。→ (本物の終了コード, 上乗せ秒)"""
    with open(証拠, "w") as f:
        f.write("起動\n")
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:                                     # ── 命令の側 ──
        os.close(r)
        try:
            t0 = time.perf_counter()
            if 掛ける:
                閉じ込める(作業場, 版)
            os.write(w, b"%f" % (time.perf_counter() - t0))
            os.close(w)
            os.chdir(作業場)
            os.execvp(argv[0], argv)
        except BaseException as ex:                   # noqa: BLE001
            os.write(2, ("子が落ちた: %r\n" % ex).encode())
            os._exit(127)
    os.close(w)
    上乗せ = float(os.read(r, 64) or b"nan")
    os.close(r)
    _, st = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(st)
    with open(証拠, "a") as f:                       # 見届け役が生きていれば書ける
        f.write("終了 %d\n" % code)
    return code, 上乗せ


# 攻撃: 命令が証拠を壊して「成功」に見せかける／見届け役を殺す。どれも本当は exit 3 で終わる
攻撃 = {
    "偽造": "open(E,'w').write('起動\\n終了 0\\n')",
    "消去": "os.unlink(E)",
    "差し替え（FIFO）": "os.unlink(E); os.mkfifo(E)",
    "切り詰め": "os.truncate(E, 0)",
    "見届け役を殺す": "os.kill(os.getppid(), signal.SIGKILL)",
}


def 一回(名, 掛ける, 版):
    """見届け役を別プロセスで走らせる（殺されても採点側は生きているように）。"""
    根 = tempfile.mkdtemp(prefix="kpoc-")
    作業場 = os.path.join(根, "作業場")
    os.mkdir(作業場)
    証拠 = os.path.join(根, "見届け.txt")         # 作業場の外
    中身 = ("import os,signal,sys\nE=%r\ntry:\n    %s\n    print('攻撃: 通った')\n"
            "except Exception as ex:\n    print('攻撃: 断られた', type(ex).__name__, ex)\nsys.exit(3)\n"
            % (証拠, 攻撃[名]))
    出 = os.path.join(根, "出力.txt")
    pid = os.fork()
    if pid == 0:
        fd = os.open(出, os.O_WRONLY | os.O_CREAT, 0o600)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        try:
            code, _ = 見届けて走らせる([sys.executable, "-c", 中身], 作業場, 証拠, 掛ける, 版)
            os._exit(0 if code == 3 else 1)
        except BaseException:                          # noqa: BLE001
            os._exit(99)
    # 見届け役が固まる攻撃（FIFO に書こうとして待ち続ける）があるので、時間を切る
    期限 = time.time() + 10
    st = None
    while time.time() < 期限:
        p, s = os.waitpid(pid, os.WNOHANG)
        if p:
            st = s
            break
        time.sleep(0.05)
    if st is None:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        # 孫（命令）も片付ける
        os.system("pkill -9 -f %r >/dev/null 2>&1" % 証拠)
        見届け役 = "固まった（10秒で打ち切り）"
    else:
        見届け役 = "生きて最後まで" if os.WIFEXITED(st) else "殺された（signal %d）" % os.WTERMSIG(st)
    # FIFO を開くと固まるので、型を先に見る
    if not os.path.lexists(証拠):
        証拠の中身 = "（無い）"
    elif not os.path.isfile(証拠) or os.path.islink(証拠):
        証拠の中身 = "（普通のファイルでない）"
    else:
        with open(証拠) as f:
            証拠の中身 = f.read()
    正直 = 証拠の中身 == "起動\n終了 3\n"
    言い分 = open(出).read().strip().splitlines()
    return {"攻撃": 名, "Landlock": 掛ける, "証拠が本物": 正直, "見届け役": 見届け役,
            "証拠": 証拠の中身.strip().replace("\n", "／"),
            "命令の言い分": next((x for x in 言い分 if x.startswith("攻撃")), "（無し）")}


def main():
    版 = abi()
    print("Landlock ABI:", 版, "／カーネル", os.uname().release)
    if 版 < 1:
        print("この機械では Landlock が使えない（%d）" % 版)
        return 2
    結果 = []
    for 掛ける in (False, True):
        for 名 in 攻撃:
            x = 一回(名, 掛ける, 版)
            結果.append(x)
            print("%s %-8s %-14s 証拠が本物=%s 見届け役=%s 証拠=%s ｜%s" % (
                "有" if 掛ける else "無", "Landlock", 名, x["証拠が本物"], x["見届け役"],
                x["証拠"], x["命令の言い分"]))
    回数 = int(sys.argv[sys.argv.index("--回数") + 1]) if "--回数" in sys.argv else 0
    上乗せ = None
    if 回数:
        計 = []
        for _ in range(回数):
            根 = tempfile.mkdtemp(prefix="kpoc-t-")
            os.mkdir(os.path.join(根, "w"))
            _, t = 見届けて走らせる(["true"], os.path.join(根, "w"), os.path.join(根, "e"), True, 版)
            計.append(t)
        上乗せ = {"回数": 回数, "中央値µs": round(statistics.median(計) * 1e6, 1),
                  "最大µs": round(max(計) * 1e6, 1)}
        print("Landlock を掛ける手間（%d回）: 中央値 %.1f µs／最大 %.1f µs" % (
            回数, 上乗せ["中央値µs"], 上乗せ["最大µs"]))
    無 = [x for x in 結果 if not x["Landlock"]]
    有 = [x for x in 結果 if x["Landlock"]]
    print(json.dumps({"ABI": 版, "カーネル": os.uname().release,
                      "Landlockなしで証拠が壊れた": sum(not x["証拠が本物"] for x in 無),
                      "Landlockありで証拠が壊れた": sum(not x["証拠が本物"] for x in 有),
                      "攻撃": len(攻撃), "上乗せ": 上乗せ}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
