"""作業場の出来事の記録（Linux・inotify）を guardrun に足す。 使い方: python3 patch_events.py 元 先

2時点の差分（before/after）は、途中で作って消したものが見えない。走っている間じゅう
作業場の出来事（作る・書き終える・消す・名前を変える）を壁の外から受け取り、
受領証の 実測.出来事 に要約を載せる。差分と突き合わせて、合わないものも名指しする。
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()


def rep(old, new):
    global s
    assert s.count(old) == 1, ("当てる場所が見つからない", old[:70], s.count(old))
    s = s.replace(old, new)


見張り = r'''
class _出来事の見張り:
    """作業場の出来事を、走っている間じゅう壁の外から受け取る（Linux の inotify）。

    **2時点の差分の穴を埋めるためのもの。**（2026-09-27・母艦）
    before/after の差し引きでは、途中で作って消したもの・一度書いて元に戻したものが
    見えない（今は「触った跡」で一部だけ拾っていた）。ここでは出来事を順に受け取り、
    受領証の 実測.出来事 に「途中で作って消したもの」と「差分と合わないもの」を残す。

    **これは壁ではなく記録。**inotify は特権なしで使えるが、限りがある：
      - 新しいフォルダに見張りを足すまでの隙間に中で作られた物は、あとで中を数えて補う
        （順番は分からない）
      - 待ち行列があふれると取りこぼす（あふれた回数を残す）
      - 見張れるフォルダの数に上限がある（見張れなかった数を残す）
    取りこぼしは黙らず数で出す。Linux 以外では「対象外」と言う。"""

    _作る, _書き終える, _消す, _出す, _入る = 0x100, 0x8, 0x200, 0x40, 0x80
    _フォルダ, _あふれ, _消えた自分 = 0x40000000, 0x4000, 0x400
    上限 = 20000

    def __init__(self, workdir, 記録d=None):
        self.根 = real(workdir)
        self.記録d = 記録d
        self.出来事 = []
        self.あふれ = 0
        self.見張れなかった = 0
        self.取得状態 = "対象外（Linux でない）"
        self._fd = None
        self._wd = {}
        self._止める = False
        self._糸 = None

    def 始める(self):
        if not sys.platform.startswith("linux"):
            return self
        try:
            import ctypes
            self._libc = ctypes.CDLL(None, use_errno=True)
            fd = self._libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            if fd < 0:
                self.取得状態 = "取得失敗（inotify_init1: errno %d）" % ctypes.get_errno()
                return self
            self._fd = fd
            for 根, dirs, _files in os.walk(self.根, followlinks=False):
                self._見張る(根)
            self.取得状態 = "取得済み"
            self._t0 = time.monotonic()
            self._糸 = threading.Thread(target=self._回す, daemon=True)
            self._糸.start()
        except Exception as ex:                             # noqa: BLE001
            self.取得状態 = "取得失敗（%s: %s）" % (type(ex).__name__, ex)
        return self

    def _見張る(self, 道):
        m = (self._作る | self._書き終える | self._消す | self._出す | self._入る | self._消えた自分)
        wd = self._libc.inotify_add_watch(self._fd, os.fsencode(道), m)
        if wd < 0:
            self.見張れなかった += 1
            return False
        self._wd[wd] = 道
        return True

    def _記す(self, 種, 道, 補い=False):
        if len(self.出来事) >= self.上限:
            self.あふれ += 1
            return
        相対 = os.path.relpath(道, self.根)
        self.出来事.append({"秒": round(time.monotonic() - self._t0, 4), "種": 種,
                            "path": 相対, **({"補い": True} if 補い else {})})

    def _読む(self):
        import struct
        try:
            buf = os.read(self._fd, 65536)
        except BlockingIOError:
            return False
        except OSError:
            return False
        i = 0
        while i + 16 <= len(buf):
            wd, mask, _cookie, n = struct.unpack_from("iIII", buf, i)
            名 = buf[i + 16:i + 16 + n].split(b"\0", 1)[0].decode("utf-8", "surrogateescape")
            i += 16 + n
            if mask & self._あふれ:
                self.あふれ += 1
                continue
            親 = self._wd.get(wd)
            if 親 is None or not 名:
                continue
            道 = os.path.join(親, 名)
            フォルダ = bool(mask & self._フォルダ)
            if mask & self._作る:
                self._記す("作る" + ("（フォルダ）" if フォルダ else ""), 道)
                if フォルダ and self._見張る(道):
                    # 見張りを足すまでの隙間に作られた物を補う（順番は分からない）
                    for 根, dirs, files in os.walk(道, followlinks=False):
                        if 根 != 道:
                            self._見張る(根)
                        for x in files:
                            self._記す("作る", os.path.join(根, x), 補い=True)
            if mask & self._入る:
                self._記す("入ってきた", 道)
            if mask & self._書き終える:
                self._記す("書き終える", 道)
            if mask & self._出す:
                self._記す("出ていった", 道)
            if mask & self._消す:
                self._記す("消す" + ("（フォルダ）" if フォルダ else ""), 道)
        return True

    def _回す(self):
        import select
        while not self._止める:
            r, _, _ = select.select([self._fd], [], [], 0.1)
            if r:
                self._読む()

    def 止める(self, 差分):
        """見張りを止め、差分と突き合わせた要約を返す。**例外を投げない。**"""
        if self._fd is None:
            return {"取得状態": self.取得状態}
        try:
            self._止める = True
            if self._糸:
                self._糸.join(1.0)
            while self._読む():
                pass
            os.close(self._fd)
        except Exception:                                   # noqa: BLE001
            pass
        self._fd = None
        件数 = {}
        for x in self.出来事:
            件数[x["種"]] = 件数.get(x["種"], 0) + 1
        最後 = {}
        作った = set()
        for x in self.出来事:
            最後[x["path"]] = x["種"]
            if x["種"].startswith("作る") or x["種"] == "入ってきた":
                作った.add(x["path"])
        残った = {c["path"] for k in ("追加", "変更") for c in (差分 or {}).get(k, [])}
        途中で消えた = sorted(p for p in 作った
                          if (最後[p].startswith("消す") or 最後[p] == "出ていった")
                          and p not in 残った)
        触られた = {x["path"] for x in self.出来事}
        合わない = sorted(c["path"] for k in ("追加", "変更", "削除")
                      for c in (差分 or {}).get(k, []) if c["path"] not in 触られた)
        要約 = {"取得状態": self.取得状態, "件数": 件数, "出来事の数": len(self.出来事),
                "途中で作って消した": 途中で消えた[:50],
                "差分にあって出来事に無い": 合わない[:50],
                "あふれ": self.あふれ, "見張れなかった": self.見張れなかった,
                "持たないもの": ["誰が（どのプロセスが）したか", "読んだこと", "属性の変更"]}
        if self.記録d:
            try:
                道 = os.path.join(self.記録d, "出来事.jsonl")
                with open(道, "w", encoding="utf-8") as f:
                    for x in self.出来事:
                        f.write(json.dumps(x, ensure_ascii=False) + "\n")
                要約["参照"] = 道
            except OSError:
                pass
        return 要約


'''
rep('''def _走る(記録d, 約束, argv, workdir, extra_writes=(),''',
    見張り.lstrip("\n") + '''def _走る(記録d, 約束, argv, workdir, extra_writes=(),''')

rep('''        before = snapshot(workdir)
''', '''        before = snapshot(workdir)
        出来事 = None          # 作業場の出来事の見張り（Linux）。起動の直前に始める
''')

rep('''        p = subprocess.Popen(
            _見届けを囲う(e, [PY, 見届け役''', '''        出来事 = _出来事の見張り(workdir, 記録d).始める()
        p = subprocess.Popen(
            _見届けを囲う(e, [PY, 見届け役''')

rep('''    d = diff(before, snapshot(workdir))
    mark, reasons = verdict(d)''', '''    d = diff(before, snapshot(workdir))
    出来事の要約 = 出来事.止める(d) if 出来事 is not None else {"取得状態": "未到達"}
    mark, reasons = verdict(d)''')

rep('''        "見届け": 見届け,
        # **消せなかった一時置き場を黙らない。**''', '''        "見届け": 見届け,
        # 走っている間の作業場の出来事（2時点の差分の穴を埋める・Linux）
        "実測": {"出来事": 出来事の要約},
        # **消せなかった一時置き場を黙らない。**''')

open(dst, "w", encoding="utf-8").write(s)
print("ok")
