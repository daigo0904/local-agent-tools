#!/bin/sh
# src/*.md を dist/*.html に変換する
cd "$(dirname "$0")"
mkdir -p dist
for f in src/*.md; do
  [ -f "$f" ] || continue
  n=$(basename "$f" .md)
  python3 conv.py "$f" > "dist/$n.html" 2>/dev/null
done
echo "ビルド完了: dist/ に出力しました"
