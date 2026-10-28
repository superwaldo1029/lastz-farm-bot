#!/bin/bash
# Installs and starts the Last Z farm bot as a background service (launchd).
# Run from the project folder with your venv active:  ./farm-start.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
ADB="$(command -v adb || true)"
[ -z "$ADB" ] && { echo "adb not found. Run: brew install android-platform-tools"; exit 1; }
"$PY" -c "import cv2, yaml" 2>/dev/null || { echo "Python libs missing. Run: source .venv/bin/activate"; exit 1; }
LABEL="com.lastz.farmbot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>$PY</string><string>$DIR/farm_bot.py</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$(dirname "$ADB"):/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$DIR/logs/bot.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/bot.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
# bootout finishes in the background; wait until the old copy is really gone
for i in $(seq 1 20); do
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || break
  sleep 0.5
done
if ! launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  sleep 2
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
fi
echo "Farm bot started. It will also start automatically when you log in."
echo "Watch it:  ./farm-status.sh      Stop it:  ./farm-stop.sh"
