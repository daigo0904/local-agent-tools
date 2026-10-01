import sys
行 = open(sys.argv[1], encoding="utf-8").read().splitlines()
出 = []
for x in 行:
    if x.startswith("# "):
        出.append("<h1>%s</h1>" % x[2:])
    elif x.strip():
        出.append("<p>%s</p>" % x)
print("\n".join(出))
