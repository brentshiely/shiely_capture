#!/bin/bash
# One-time setup: venv with dependencies + a signed ShielyCapture.app wrapper.
# Needs Homebrew Python (brew install python). Does not use /usr/bin/python3.
set -e
D="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3}"
[ -x "$PY" ] || { echo "Homebrew python not found at $PY (set PYTHON=/path/to/python3)"; exit 1; }

echo "== venv"
rm -rf "$D/venv"
"$PY" -m venv "$D/venv"
"$D/venv/bin/pip" install -q -r "$D/requirements.txt"

echo "== ShielyCapture.app"
BASE="$("$PY" -c 'import sys; print(sys.base_prefix)')"
SRC="$BASE/Resources/Python.app"
APP="$D/ShielyCapture.app"
[ -d "$SRC" ] || { echo "Python.app not found at $SRC"; exit 1; }
rm -rf "$APP"
cp -R "$SRC" "$APP"
mv "$APP/Contents/MacOS/Python" "$APP/Contents/MacOS/ShielyCapture"
rm -rf "$APP/Contents/_CodeSignature"
I="$APP/Contents/Info.plist"
plutil -replace CFBundleExecutable -string ShielyCapture "$I"
plutil -replace CFBundleName -string ShielyCapture "$I"
plutil -replace CFBundleDisplayName -string ShielyCapture "$I"
plutil -replace CFBundleIdentifier -string com.brentshiely.ShielyCapture "$I"
plutil -replace LSUIElement -bool true "$I"
plutil -remove CFBundleDocumentTypes "$I" 2>/dev/null || true
plutil -remove CFBundleURLTypes "$I" 2>/dev/null || true
codesign --force --deep -s - "$APP"

echo "done. Next: ./start.sh, then grant Screen Recording to ShielyCapture when asked."
