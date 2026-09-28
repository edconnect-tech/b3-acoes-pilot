#!/usr/bin/env bash
# Configura o agendador nativo do macOS (launchd) para rodar o alerta matinal às 09:15 BRT (Seg-Sex)

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.b3pilot.morning.plist"
SCRIPT_PATH="/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot"

mkdir -p "$PLIST_DIR"

cat << EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.b3pilot.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_PATH</string>
        <string>alert</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Segunda-feira às 09:15 -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
        <!-- Terça-feira às 09:15 -->
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
        <!-- Quarta-feira às 09:15 -->
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
        <!-- Quinta-feira às 09:15 -->
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
        <!-- Sexta-feira às 09:15 -->
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>15</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>/tmp/b3pilot_morning.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/b3pilot_morning_err.log</string>
</dict>
</plist>
EOF

echo "✓ LaunchAgent criado em $PLIST_FILE"
echo "Para ativar o agendamento no macOS, execute:"
echo "launchctl load $PLIST_FILE"
