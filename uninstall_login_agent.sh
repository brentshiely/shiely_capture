#!/bin/bash
L=com.brentshiely.shiely-capture
launchctl bootout gui/$(id -u)/$L 2>/dev/null || true
rm -f ~/Library/LaunchAgents/$L.plist
echo "removed: $L"
