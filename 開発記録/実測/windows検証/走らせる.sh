#!/bin/bash
# リセット後の検証を1回で回す。 使い方: ~/未踏/実測/windows検証/走らせる.sh [--予行]
#   1. その時点の ~/bin の guardrun 一式を写し、sid 版と対照版をパッチで作る
#   2. guardrun-portability に push して reset-check を走らせる
#   3. 終わるのを待ってログを取り、集計.py で 判定基準.md の各項目を判定する
# 本物の ~/bin は触らない（sid を入れるかは結果を見て決める）。
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
DAY="$(date +%Y%m%d-%H%M)"
R=ahogorirappa/guardrun-portability
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT

echo "▶ 写しを作る"
gh repo clone "$R" "$W/gp" -- -q
cd "$W/gp"
mkdir -p t bin .github/workflows
cp ~/bin/guardrun.py ~/bin/guardrun-印の試験 ~/bin/guardrun-実測 ~/bin/guardlib.py bin/
python3 "$D/patch_sid.py"  bin/guardrun.py bin/guardrun.sid.py
python3 "$D/patch_ctl2.py" bin/guardrun.py bin/guardrun.ctl2.py
cp "$D"/t_*.py t/
cp "$D/reset-check.yml" .github/workflows/
echo "  guardrun の版: $(cd ~/bin && git log --oneline -1 -- guardrun.py)"
python3 -c "import ast,sys;[ast.parse(open(f,encoding='utf-8').read()) for f in sys.argv[1:]]" bin/guardrun.py bin/guardrun.sid.py bin/guardrun.ctl2.py t/*.py
if [ "${1:-}" = "--予行" ]; then
  echo "✓ 予行: 組み立てまで通った（push はしない）"; ls bin/guardrun*.py t/ .github/workflows/reset-check.yml; exit 0
fi
git add -A
git commit -q -m "reset-check: $(cd ~/bin && git log --oneline -1 -- guardrun.py | cut -c1-60)" || true
git push -q

echo "▶ 走らせる"
gh workflow run reset-check.yml -R "$R"
sleep 8
ID="$(gh run list -R "$R" -w reset-check -L1 --json databaseId --jq '.[0].databaseId')"
echo "  run $ID  https://github.com/$R/actions/runs/$ID"
gh run watch "$ID" -R "$R" >/dev/null 2>&1 || true

LOG="$D/log-$DAY.txt"
gh run view "$ID" -R "$R" --log > "$LOG" 2>/dev/null || true
if ! grep -q "【" "$LOG"; then
  echo "✗ 出力がありません。枠が戻っていない可能性があります:"
  gh run view "$ID" -R "$R" 2>&1 | grep -iE "spending|payment|billing|not started" | head -3
  exit 1
fi
python3 "$D/集計.py" "$LOG" > "$D/結果-$DAY.md"
cat "$D/結果-$DAY.md"
echo
echo "結果: $D/結果-$DAY.md　ログ: $LOG"
