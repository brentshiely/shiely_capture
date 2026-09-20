#!/bin/bash
# Start ShielyCapture via LaunchServices so macOS permissions attach to "ShielyCapture".
D="$(cd "$(dirname "$0")" && pwd)"
SP="$(echo "$D"/venv/lib/python*/site-packages)"
pkill -f "$D/shiely_capture.py" 2>/dev/null; sleep 0.5
open -n --stdout "$HOME/Library/Logs/shiely_capture.log" --stderr "$HOME/Library/Logs/shiely_capture.log" \
  --env PYTHONPATH="$SP" "$D/ShielyCapture.app" --args "$D/shiely_capture.py"
echo "started. log: ~/Library/Logs/shiely_capture.log"
