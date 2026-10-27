#!/bin/bash
# Shows whether the bot is running, then follows the log (Ctrl+C to stop watching; the bot keeps running).
LABEL="com.lastz.farmbot"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then echo "Status: RUNNING"; else echo "Status: STOPPED"; fi
echo "---- recent log ----"
tail -n 30 -f "$(cd "$(dirname "$0")" && pwd)/logs/bot.log"
