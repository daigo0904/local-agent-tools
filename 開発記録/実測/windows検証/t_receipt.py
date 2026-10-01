import importlib.util, importlib.machinery, os, sys, json, tempfile, tarfile
P=sys.argv[1]
spec=importlib.util.spec_from_loader("g",importlib.machinery.SourceFileLoader("g",P)); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
根=tempfile.mkdtemp(prefix="rc-")
def 走る(code, 期待=None, 名=""):
    w=tempfile.mkdtemp(prefix="rw-", dir="/Users/Shared" if sys.platform=="darwin" else None)
    os.chmod(w,0o777)
    open(os.path.join(w,"前からある.txt"),"w").write("もと\n")
    r=g.run([g.PY,"-c",code], w, prove=False, 記録=根, 期待=期待, wall_sec=20)
    rc=json.load(open(r["受領証"]))
    tar=rc["実測"]["初期資料"]
    names=tarfile.open(tar["参照"]).getnames() if tar.get("参照") else None
    段=[json.loads(x)["段階"] for x in open(rc["実測"]["段階"])] if rc["実測"]["段階"] else None
    print("==",名,"| 判定",rc["判定"],"| 照合",rc["事後"]["照合"],"| 初期資料",tar["取得状態"],names,"| 段階",段,"| 版",rc["形式版"],"| sha",(rc["実測"]["起動資料"].get("guardrun_sha256") or "")[:8])
走る("open('a','w').write('x')", {"判定":"緑","終了コード":0,"差分":{"追加":["a"]}}, "期待どおり")
走る("pass", {"判定":"緑","差分":{"追加":["a"]}}, "期待と違う")
走る("open('a','w').write('x')", None, "宣言なし")
