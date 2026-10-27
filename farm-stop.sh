#!/bin/bash
# Stops the farm bot and removes it from login startup.
LABEL="com.lastz.farmbot"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Farm bot stopped." || echo "Farm bot was not running."
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
