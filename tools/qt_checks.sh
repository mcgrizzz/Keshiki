#!/usr/bin/env bash
# Run every real-Anki check offscreen with the current python, which needs aqt
# and its Qt dependencies. Pass --screenshots DIR to keep screenshots.
set -euo pipefail
cd "$(dirname "$0")"
export KISO_STRICT_ANKI_NOTICES=1   # fail on any Anki deprecation notice
for check in check_main_window check_settings check_addon; do
  echo "== $check"
  timeout -k 10 300 python "$check.py" "$@"
done
