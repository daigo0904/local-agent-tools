"""対照: 秘密の証明で「親フォルダごと読みの穴」をわざと開ける版を作る。 使い方: python3 patch_ctl2.py 元 先"""
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
old = '    run([PY, "-c", 読む, 先], 場, wall_sec=20, enforcer=e, prove=False, 記録=記録根)'
assert s.count(old) == 1, "当てる場所が見つからない"
s = s.replace(old, old[:-1] + ',\n        extra_reads=((os.path.dirname(先),) if 名.startswith("秘") else ()))  # 対照: 親ごと読みの穴')
open(dst, "w", encoding="utf-8").write(s)
print("ok")
