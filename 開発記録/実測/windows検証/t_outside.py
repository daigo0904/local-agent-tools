# Linux: 作業場の外に書いたとき、壁の中からどう見えるか・外に残るか
import importlib.util, importlib.machinery, os, sys, json, tempfile
P=sys.argv[1]
spec=importlib.util.spec_from_loader("g",importlib.machinery.SourceFileLoader("g",P)); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
H=os.path.expanduser("~")
for 的 in [os.path.join(H,"外.txt"), "/tmp/外.txt", "/var/tmp/外.txt", os.path.join(H,".config","外.txt")]:
    w=tempfile.mkdtemp(prefix="ow-"); os.chmod(w,0o777)
    code=("import os,json\nr={}\ntry:\n open(%r,'w').write('ng'); r['書けた']=True\nexcept Exception as e: r['書けた']=repr(e)\n"
          "r['中で見える']=os.path.exists(%r)\nr['HOME']=os.environ.get('HOME')\nr['uid']=os.getuid()\n"
          "import subprocess\nr['mounts']=[l.split()[1]+' '+l.split()[0]+' '+l.split()[3][:20] for l in open('/proc/self/mounts') if l.split()[1] in ('/','/tmp','/var/tmp',%r,'/home')]\n"
          "open('r.json','w').write(json.dumps(r))") % (的, 的, H)
    r=g.run([g.PY,"-c",code], w, prove=False, 記録=tempfile.mkdtemp(), wall_sec=30)
    中=json.load(open(os.path.join(w,"r.json"))) if os.path.exists(os.path.join(w,"r.json")) else None
    print("的",的,"| 判定",r["判定"],r.get("終了コード"),"| 中",中,"| 外に残った",os.path.exists(的))
    try: os.unlink(的)
    except OSError: pass
