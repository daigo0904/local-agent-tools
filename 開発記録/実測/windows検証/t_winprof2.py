"""Windows: 今の版（now）と SID 使い回し版（sid）の1回あたりの時間を、交互に比べる。

2通りで測る:
  同じプロセス  run() を毎回 enforcer なしで呼ぶ（実測・印の試験・証明の使い方）
  コマンド      guardrun.py <作業場> <命令> を毎回別のプロセスで起こす（ふつうの使い方）
どの回も 判定・終了コード・書けたか を出す（走っていない回を速いと読まないため）。
使い方: python t_winprof2.py guardrun.now.py guardrun.sid.py [回数]
"""
import importlib.machinery, importlib.util, json, os, statistics, subprocess, sys, tempfile, time
A, B = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 6
def 読み込む(p, 名):
    spec = importlib.util.spec_from_loader(名, importlib.machinery.SourceFileLoader(名, p))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
版 = {"now": 読み込む(A, "g_now"), "sid": 読み込む(B, "g_sid")}
道 = {"now": A, "sid": B}
命令 = "open('a','w').write('x')"
def 作業場():
    # Mac は /var/folders に ACL を付けられず拒否になる（2026-09-24 の予行で 4通りとも拒否）
    w = tempfile.mkdtemp(dir="/Users/Shared" if sys.platform == "darwin" else None)
    if os.name != "nt":
        os.chmod(w, 0o777)
    return w
結果 = {(k, 形): [] for k in 版 for 形 in ("同じプロセス", "コマンド")}
根 = tempfile.mkdtemp()
for k, g in 版.items():                               # 温める（数えない）
    g.run([sys.executable, "-c", 命令], 作業場(), 記録=根)
for i in range(N):
    順 = ["now", "sid"] if i % 2 == 0 else ["sid", "now"]   # 順番の効果を消す
    for k in 順:
        w = 作業場()
        t = time.perf_counter(); r = 版[k].run([sys.executable, "-c", 命令], w, 記録=根); 秒 = time.perf_counter() - t
        結果[(k, "同じプロセス")].append((秒, r["判定"], r.get("終了コード"), os.path.exists(os.path.join(w, "a"))))

# ── コマンド：版ごとにまとめて走らせる（ABBA）──
# 証明の控えは1つだけで、guardrun.py の更新時刻と大きさが変わると取り直す（_証明の指紋）。
# 版を交互に起こすと毎回証明を取り直し、SID ではなく証明の時間を測ってしまう
# （2026-09-24 の Mac の予行で 1回 17〜35秒）。まとまりの頭で1回温めてから数える。
def コマンドで(k, 数える):
    w = 作業場()
    t = time.perf_counter()
    o = subprocess.run([sys.executable, 道[k], w, sys.executable, "-c", 命令], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    秒 = time.perf_counter() - t
    try:
        r = json.loads(o.stdout)
    except Exception:
        r = {"判定": "読めない", "終了コード": None}
    if 数える:
        結果[(k, "コマンド")].append((秒, r.get("判定"), r.get("終了コード"), os.path.exists(os.path.join(w, "a"))))
for k in ("now", "sid", "sid", "now"):
    コマンドで(k, False)
    for _ in range(max(1, N // 2)):
        コマンドで(k, True)
まとめ = {}
for (k, 形), xs in 結果.items():
    ちゃんと = [x for x in xs if x[1] == "緑" and x[2] == 0 and x[3]]
    まとめ["%s・%s" % (形, k)] = {"中央値ms": round(statistics.median(x[0] for x in xs) * 1000),
                                "緑で書けた": "%d/%d" % (len(ちゃんと), len(xs)),
                                "判定": sorted({str(x[1]) for x in xs})}
    print("%-10s %-4s 中央値 %5d ms  緑で書けた %s  判定 %s" % (形, k, まとめ["%s・%s" % (形, k)]["中央値ms"],
          まとめ["%s・%s" % (形, k)]["緑で書けた"], まとめ["%s・%s" % (形, k)]["判定"]))
print("まとめ", json.dumps(まとめ, ensure_ascii=False))
