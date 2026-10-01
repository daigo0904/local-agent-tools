#!/bin/sh
cd "$(dirname "$0")"
( python3 走らせる.py --系統 codex,claude --課題 E1,E2,E3 --回数 3 > 走り-E本番.log 2>&1
  python3 走らせる.py --系統 codex --課題 D1,D2 --回数 1 > 走り-D追加a.log 2>&1
  python3 走らせる.py --系統 codex --課題 D3 --回数 2 > 走り-D追加b.log 2>&1 ) &
( sleep 65; python3 走らせる.py --系統 openclaw --課題 E1,E2,E3 --回数 3 > 走り-E参考openclaw.log 2>&1 ) &
wait
echo 全部終わり
