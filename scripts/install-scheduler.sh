#!/bin/bash
# 安装 launchd 定时任务（每周一 06:00 自动运行）
set -e

PLIST_SRC="$(dirname "$0")/../launchd/com.yoli.agent-radar.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.yoli.agent-radar.plist"

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
echo "✅ 已安装：每周一 06:00 自动生成 agent-radar 周报"
echo "   查看状态：launchctl list | grep agent-radar"
echo "   手动触发：launchctl start com.yoli.agent-radar"
echo "   卸载：launchctl unload $PLIST_DST && rm $PLIST_DST"
