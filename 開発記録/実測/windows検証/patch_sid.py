"""SID の使い回し（Windows）を guardrun.py に当てる。 使い方: python3 patch_sid.py 元 先"""
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, ("当てる場所が見つからない（guardrun が変わった）", old[:60], s.count(old))
    s = s.replace(old, new)
rep('''    def _sid(self):
        if self._sid値 is None:
            o = self._走らす(''', '''    def _sid(self):
        # **SID はプロセスの中で使い回す。**（2026-09-24・母艦）
        # pick_enforcer() は走りのたびに新しい執行を作るので、1回ごとに PowerShell を
        # 起こして引き直していた（GitHub windows-2025 で 1回目 779ms のうち 637ms がこの1回）。
        # 引けなかった結果（""）は控えない（あとで利用者を作った場合に引き直せるように）。
        # **ディスクには控えない。**利用者を作り直すと SID が変わり、古い SID で通信の規則を
        # 作ると黙って素通しになる。
        if self._sid値 is None and _SIDの控え.get(self.利用者):
            self._sid値 = _SIDの控え[self.利用者]
        if self._sid値 is None:
            o = self._走らす(''')
rep('''            self._sid値 = 値 if 値.startswith("S-1-") else ""
        return self._sid値''', '''            self._sid値 = 値 if 値.startswith("S-1-") else ""
            if self._sid値:
                _SIDの控え[self.利用者] = self._sid値
        return self._sid値''')
rep('''def pick_enforcer():''', '''_SIDの控え = {}     # 利用者名 → SID（Windows。プロセスの中だけ）


def pick_enforcer():''')
open(dst, "w", encoding="utf-8").write(s)
print("ok")
