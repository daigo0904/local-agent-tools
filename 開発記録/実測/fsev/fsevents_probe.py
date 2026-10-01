#!/usr/bin/env python3
"""FSEvents（macOS・特権なし）で、guardrun の走りの間の作業場の出来事を取れるかを測る試作。

    python3 fsevents_probe.py [回数]

3通り（途中で書いて消す・フォルダごと作って消す・書くだけ）を guardrun の壁の中で走らせ、
走っている間の出来事を壁の外から FSEvents で受け取る。各通りを 回数 回くり返し、
取りこぼし（期待した名前が「作って消した」に出ない回）と、落とした印（Dropped/MustScanSubDirs）を数える。
"""
import ctypes
import ctypes.util
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time

CS = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
LD = ctypes.CDLL(ctypes.util.find_library("System"))

CF.CFStringCreateWithCString.restype = ctypes.c_void_p
CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
CF.CFArrayCreate.restype = ctypes.c_void_p
CF.CFArrayCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_long, ctypes.c_void_p]
CF.CFRelease.argtypes = [ctypes.c_void_p]
kCFTypeArrayCallBacks = ctypes.c_void_p.in_dll(CF, "kCFTypeArrayCallBacks")

CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                            ctypes.POINTER(ctypes.c_uint64))
CS.FSEventStreamCreate.restype = ctypes.c_void_p
CS.FSEventStreamCreate.argtypes = [ctypes.c_void_p, CALLBACK, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_uint64, ctypes.c_double, ctypes.c_uint32]
for f in ("FSEventStreamStart", "FSEventStreamFlushSync", "FSEventStreamStop",
          "FSEventStreamInvalidate", "FSEventStreamRelease"):
    getattr(CS, f).argtypes = [ctypes.c_void_p]
CS.FSEventStreamStart.restype = ctypes.c_bool
CS.FSEventStreamSetDispatchQueue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
LD.dispatch_queue_create.restype = ctypes.c_void_p
LD.dispatch_queue_create.argtypes = [ctypes.c_char_p, ctypes.c_void_p]

SINCE_NOW = 0xFFFFFFFFFFFFFFFF
FLAG_NO_DEFER, FLAG_FILE_EVENTS = 0x2, 0x10
印 = {0x100: "作る", 0x200: "消す", 0x800: "名前変更", 0x1000: "書く", 0x400: "属性"}
落とした印 = {0x1: "下を調べ直せ", 0x2: "利用者側で落とした", 0x4: "カーネルで落とした"}
フォルダ印 = 0x20000


class 見張り:
    def __init__(self, 根):
        self.根 = os.path.realpath(根)
        self.出来事 = []
        self.落とした = []
        self._鍵 = threading.Lock()
        self._cb = CALLBACK(self._受ける)          # 参照を持っておく（消えると落ちる）

    def _受ける(self, _s, _i, n, paths, flags, _ids):
        arr = ctypes.cast(paths, ctypes.POINTER(ctypes.c_char_p))
        with self._鍵:
            for k in range(n):
                p = arr[k].decode("utf-8", "surrogateescape")
                fl = flags[k]
                for b, 名 in 落とした印.items():
                    if fl & b:
                        self.落とした.append(名)
                if not (p == self.根 or p.startswith(self.根 + "/")):
                    continue
                種 = [名 for b, 名 in 印.items() if fl & b]
                self.出来事.append({"path": os.path.relpath(p, self.根), "種": 種,
                                    "フォルダ": bool(fl & フォルダ印)})

    def 始める(self):
        s = CF.CFStringCreateWithCString(None, self.根.encode(), 0x08000100)
        a = (ctypes.c_void_p * 1)(s)
        arr = CF.CFArrayCreate(None, a, 1, ctypes.addressof(kCFTypeArrayCallBacks))
        self._st = CS.FSEventStreamCreate(None, self._cb, None, arr, SINCE_NOW, 0.0,
                                          FLAG_NO_DEFER | FLAG_FILE_EVENTS)
        q = LD.dispatch_queue_create(b"guardrun.fsevents", None)
        CS.FSEventStreamSetDispatchQueue(self._st, q)
        if not CS.FSEventStreamStart(self._st):
            raise OSError("FSEventStreamStart に失敗")
        time.sleep(0.05)                                   # 始まるのを待つ
        return self

    def 止める(self):
        CS.FSEventStreamFlushSync(self._st)
        CS.FSEventStreamStop(self._st)
        CS.FSEventStreamInvalidate(self._st)
        CS.FSEventStreamRelease(self._st)
        with self._鍵:
            return list(self.出来事), list(self.落とした)


def 作って消した(出来事, 残った):
    """作るの印があり、最後に消すの印がある（か同じ出来事に両方ある）もので、差分に残っていないもの。"""
    最後 = {}
    作った = set()
    for x in 出来事:
        if "作る" in x["種"]:
            作った.add(x["path"])
        最後[x["path"]] = x["種"]
    return sorted(p for p in 作った if "消す" in 最後[p] and p not in 残った)


def main():
    回数 = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    spec = importlib.util.spec_from_loader("g", importlib.machinery.SourceFileLoader(
        "g", os.path.expanduser("~/bin/guardrun.py")))
    g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
    ケース = [
        ("途中で書いて消す", "import os\nopen('tmp.txt','w').write('x')\nos.unlink('tmp.txt')\nopen('a','w').write('y')",
         {"tmp.txt"}),
        ("フォルダごと作って消す", "import os,shutil\nos.makedirs('d/e')\nopen('d/e/f','w').write('1')\n"
         "open('d/g','w').write('2')\nshutil.rmtree('d')", {"d", "d/e", "d/e/f", "d/g"}),
        ("書くだけ", "open('b','w').write('z')\nopen('前.txt','a').write('+')", set()),
    ]
    まとめ = {}
    for 名, 中, 期待 in ケース:
        取れた回, 合わない回, 落とした回, 例 = 0, 0, 0, None
        for _ in range(回数):
            w = tempfile.mkdtemp(dir="/Users/Shared"); os.chmod(w, 0o777)
            with open(os.path.join(w, "前.txt"), "w") as f:
                f.write("もと\n")
            見 = 見張り(w).始める()
            r = g.run([g.PY, "-c", 中], w, prove=False, 記録=tempfile.mkdtemp(), wall_sec=20)
            出, 落 = 見.止める()
            残った = {c["path"] for k in ("追加", "変更") for c in r["差分"][k]}
            消えた = set(作って消した(出, 残った))
            触られた = {x["path"] for x in 出}
            差分の名 = {c["path"] for k in ("追加", "変更", "削除") for c in r["差分"][k]}
            if 期待 <= 消えた:
                取れた回 += 1
            elif 例 is None:
                例 = {"取れた": sorted(消えた), "出来事": 出[:20]}
            if 差分の名 - 触られた:
                合わない回 += 1
            if 落:
                落とした回 += 1
        まとめ[名] = {"期待どおり取れた": "%d/%d" % (取れた回, 回数), "差分と合わない回": 合わない回,
                     "落とした印が出た回": 落とした回, **({"取りこぼした例": 例} if 例 else {})}
        print(名, json.dumps(まとめ[名], ensure_ascii=False))
    print(json.dumps({"macOS": os.uname().release, "回数": 回数, "まとめ": まとめ}, ensure_ascii=False))


if __name__ == "__main__":
    main()
