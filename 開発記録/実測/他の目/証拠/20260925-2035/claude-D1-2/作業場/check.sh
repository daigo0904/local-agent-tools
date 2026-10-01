#!/bin/sh
# 試験を走らせる
cd "$(dirname "$0")"
python3 tests/test_mul.py || { echo "失敗した試験があります"; exit 1; }
echo "すべての試験が通りました"
