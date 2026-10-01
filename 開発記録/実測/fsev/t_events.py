import importlib.machinery, importlib.util, os, sys, tempfile, json
spec = importlib.util.spec_from_loader("g", importlib.machinery.SourceFileLoader("g", sys.argv[1]))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
ケース = [
 ("途中で書いて消す", "import os\nopen('tmp.txt','w').write('x')\nos.unlink('tmp.txt')\nopen('a','w').write('y')"),
 ("フォルダごと作って消す", "import os,shutil\nos.makedirs('d/e')\nopen('d/e/f','w').write('1')\nopen('d/g','w').write('2')\nshutil.rmtree('d')"),
 ("書くだけ", "open('b','w').write('z')\nopen('前.txt','a').write('+')"),
]
for 名, 中 in ケース:
    w = tempfile.mkdtemp(dir="/Users/Shared" if sys.platform == "darwin" else None); os.chmod(w, 0o777)
    open(os.path.join(w, "前.txt"), "w").write("もと\n")
    r = g.run([g.PY, "-c", 中], w, prove=False, 記録=tempfile.mkdtemp(), wall_sec=20)
    d = {k: [c["path"] for c in v] for k, v in r["差分"].items()}
    e = (r.get("実測") or {}).get("出来事")
    print("==", 名, "| 判定", r["判定"], "| 差分", d)
    print("   出来事", json.dumps({k: e.get(k) for k in ("取得状態", "件数", "途中で作って消した", "差分にあって出来事に無い", "あふれ", "見張れなかった")} if e else None, ensure_ascii=False))
