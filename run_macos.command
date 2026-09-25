#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
for candidate in python3 python python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;sys.exit(sys.version_info[:2] < (3,8))' 2>/dev/null; then
    exec "$candidate" -X utf8 run_all.py "$@"
  fi
done
printf '%s\n' '请先安装可用的Python 3.8或更新版本。复现所需环境会自动准备。'
exit 1
