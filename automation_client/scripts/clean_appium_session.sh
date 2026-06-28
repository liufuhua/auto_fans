#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

detect_udid() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

UDID="${1:-${DEFAULT_UDID:-}}"
SYSTEM_PORT="${2:-${DEFAULT_SYSTEM_PORT:-8202}}"

if [[ -z "$UDID" ]]; then
  ONLINE_UDIDS="$(detect_udid)"
  ONLINE_COUNT="$(printf "%s\n" "$ONLINE_UDIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$ONLINE_COUNT" != "1" ]]; then
    echo "未指定设备，且当前在线设备数量不是 1。"
    echo "请指定 UDID：scripts/clean_appium_session.sh <udid> <system_port>"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

echo "clean appium session: udid=$UDID systemPort=$SYSTEM_PORT"

adb -s "$UDID" forward --remove "tcp:$SYSTEM_PORT" || true

adb -s "$UDID" shell am force-stop io.appium.uiautomator2.server || true
adb -s "$UDID" shell am force-stop io.appium.uiautomator2.server.test || true

adb -s "$UDID" shell pkill -f uiautomator || true

echo "remaining adb forwards:"
adb forward --list || true

echo "done"
