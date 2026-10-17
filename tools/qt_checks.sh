#!/usr/bin/env bash
# Run every real-Anki check offscreen with the current python, which needs aqt
# and its Qt dependencies. Pass --screenshots DIR to keep screenshots. Every check
# runs even after one fails, so a CI run shows all that fail; then it fails too.
set -uo pipefail
cd "$(dirname "$0")"
export KISO_STRICT_ANKI_NOTICES=1   # fail on any Anki deprecation notice
failed=()
for check in check_main_window check_launch check_settings check_display check_addon; do
  echo "== $check"
  timeout -k 10 300 python "$check.py" "$@" || failed+=("$check")
done
if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
