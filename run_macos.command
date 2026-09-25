#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
for candidate in python3.12 python3.13 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;sys.exit(sys.version_info[:2] not in [(3,12),(3,13)])' 2>/dev/null; then
    exec "$candidate" -X utf8 run_all.py "$@"
  fi
done
printf '%s\n' '请先安装64位Python 3.12或3.13，然后重新运行。'
exit 1
