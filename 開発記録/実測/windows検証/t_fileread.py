# Windows: 読める場所にファイルを1つ名指しして、壁の中から読めるか
import importlib.util, importlib.machinery, os, sys, json, tempfile
P=sys.argv[1]
spec=importlib.util.spec_from_loader("g",importlib.machinery.SourceFileLoader("g",P)); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
外=tempfile.mkdtemp(prefix="fr-"); f=os.path.join(外,"読ませたい.txt"); open(f,"w").write("x"*77)
w=tempfile.mkdtemp(prefix="fw-")
code="n=0\ntry: n=len(open(%r,'rb').read())\nexcept Exception as e: n=repr(e)\nopen('n','w').write(str(n))" % f
r=g.run([g.PY,"-c",code], w, prove=False, extra_reads=(f,), 記録=tempfile.mkdtemp(), wall_sec=30)
print("ファイル1つの許可:", open(os.path.join(w,"n")).read() if os.path.exists(os.path.join(w,"n")) else "（数が無い）", "判定", r["判定"])
