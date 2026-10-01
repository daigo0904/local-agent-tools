#!/bin/sh
# src/*.md を dist/*.html に変換する
cd "$(dirname "$0")"
mkdir -p dist
for f in src/*.md; do
  [ -e "$f" ] || continue
  n=$(basename "$f" .md)
  python3 conv.py "$f" > "dist/$n.html" || { echo "失敗: $f" >&2; exit 1; }
done
echo "ビルド完了: dist/ に出力しました"
