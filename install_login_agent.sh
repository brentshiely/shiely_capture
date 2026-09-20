#!/bin/bash
# Start ShielyCapture now and at every login. Quit from the menu bar stays quit
# (launchd only restarts it after a crash).
set -e
D="$(cd "$(dirname "$0")" && pwd)"
L=com.brentshiely.shiely-capture
SP="$(echo "$D"/venv/lib/python*/site-packages)"
LOG="$HOME/Library/Logs/shiely_capture.log"
cat > "$HOME/Library/LaunchAgents/$L.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$L</string>
    <key>ProgramArguments</key>
    <array>
        <string>$D/ShielyCapture.app/Contents/MacOS/ShielyCapture</string>
        <string>$D/shiely_capture.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONPATH</key><string>$SP</string></dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>ProcessType</key><string>Interactive</string>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
launchctl bootout gui/$(id -u)/$L 2>/dev/null || true
# bootout is asynchronous; retry bootstrap until launchd has finished tearing down
for i in 1 2 3 4 5 6 7 8; do
    launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/$L.plist" 2>/dev/null && break
    sleep 0.5
done
echo "installed and started: $L"
