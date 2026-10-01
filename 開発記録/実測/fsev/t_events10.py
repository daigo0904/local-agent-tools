import importlib.machinery, importlib.util, os, sys, tempfile
spec = importlib.util.spec_from_loader("g", importlib.machinery.SourceFileLoader("g", sys.argv[1]))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
期待 = {"d", "d/e", "d/e/f", "d/g"}
中 = "import os,shutil\nos.makedirs('d/e')\nopen('d/e/f','w').write('1')\nopen('d/g','w').write('2')\nshutil.rmtree('d')"
取れた, 印あり, 落 = 0, 0, []
for _ in range(10):
    w = tempfile.mkdtemp(); os.chmod(w, 0o777)
    e = g.run([g.PY, "-c", 中], w, prove=False, 記録=tempfile.mkdtemp(), wall_sec=20)["実測"]["出来事"]
    got = set(e["途中で作って消した"])
    if 期待 <= got: 取れた += 1
    else: 落.append(sorted(期待 - got))
    if e["あふれ"] or e["見張れなかった"]: 印あり += 1
print("Linux inotify 10回: 期待どおり %d/10・取りこぼしの印が出た回 %d・落とした名前 %s" % (取れた, 印あり, 落[:3]))
