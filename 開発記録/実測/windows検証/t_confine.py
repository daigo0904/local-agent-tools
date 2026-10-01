"""Linux: この機械の Landlock の版と、guardrun の走りに「閉じ込め」が掛かったかを出す。"""
import ctypes, importlib.machinery, importlib.util, json, os, sys, tempfile
spec = importlib.util.spec_from_loader("g", importlib.machinery.SourceFileLoader("g", sys.argv[1]))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
libc = ctypes.CDLL(None, use_errno=True); libc.syscall.restype = ctypes.c_long
版 = libc.syscall(444, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
try:
    lsm = open("/sys/kernel/security/lsm").read().strip()
except OSError as e:
    lsm = "読めない %s" % e
w = tempfile.mkdtemp(); os.chmod(w, 0o777)
r = g.run([sys.executable, "-c", "open('a','w').write('x')"], w, prove=False, 記録=tempfile.mkdtemp(), wall_sec=20)
print("閉じ込め", json.dumps({"カーネル": os.uname().release, "LSM": lsm, "Landlock版": 版,
      "判定": r["判定"], "閉じ込め": (r.get("見届け") or {}).get("閉じ込め")}, ensure_ascii=False))
