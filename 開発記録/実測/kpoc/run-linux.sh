#!/bin/sh
# 使い方: run-linux.sh <guardrun.py の場所> [追加の命令]
G=$1; shift
docker run --rm --privileged -v ~/bin:/bin2:ro -v "$(dirname $G)":/g:ro -v /private/tmp/claude-501/-Users-daigo/27e58d1d-918b-498f-ba7f-f07bb332a54f/scratchpad/kpoc:/k:ro gr-linux sh -c "mkdir -p b && cp /bin2/guardrun-印の試験 /bin2/guardrun-実測 /bin2/guardlib.py b/ && cp /g/$(basename $G) b/guardrun.py && cd b && $*"
