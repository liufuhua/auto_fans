#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

detect_udid() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

default_system_port() {
  case "$1" in
    FMR0223830012928) echo "8201" ;;
    adb-10AG3R2JNF001KK-WGRLsd._adb-tls-connect._tcp) echo "8202" ;;
    R5CW11CKN0B) echo "8203" ;;
    *) echo "8201" ;;
  esac
}

UDID="${1:-${DEFAULT_UDID:-}}"
if [[ -z "$UDID" ]]; then
  ONLINE_UDIDS="$(detect_udid)"
  ONLINE_COUNT="$(printf "%s\n" "$ONLINE_UDIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$ONLINE_COUNT" != "1" ]]; then
    echo "未指定设备，且当前在线设备数量不是 1。"
    echo "用法：scripts/clear_session.sh <udid> [system_port]"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

SYSTEM_PORT="${2:-${DEFAULT_SYSTEM_PORT:-$(default_system_port "$UDID")}}"

echo "清理 Appium session：udid=$UDID systemPort=$SYSTEM_PORT"

echo "1. 清理 adb forward"
adb -s "$UDID" forward --remove "tcp:$SYSTEM_PORT" || true

echo "2. 停止设备上的 Appium / UiAutomator2 服务"
adb -s "$UDID" shell am force-stop io.appium.uiautomator2.server || true
adb -s "$UDID" shell am force-stop io.appium.uiautomator2.server.test || true
adb -s "$UDID" shell pkill -f uiautomator || true

echo "3. 当前 adb forward 列表"
adb forward --list || true

echo "清理完成"
