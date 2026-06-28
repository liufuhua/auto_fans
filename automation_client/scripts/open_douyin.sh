#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

detect_udid() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

default_device_name() {
  case "$1" in
    FMR0223830012928) echo "device_01" ;;
    adb-10AG3R2JNF001KK-WGRLsd._adb-tls-connect._tcp) echo "device_02" ;;
    R5CW11CKN0B) echo "device_03" ;;
    *) echo "device_01" ;;
  esac
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
    echo "请指定 UDID：scripts/open_douyin.sh <udid> <device_name> <system_port>"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

DEVICE_NAME="${2:-${DEFAULT_DEVICE_NAME:-$(default_device_name "$UDID")}}"
SYSTEM_PORT="${3:-${DEFAULT_SYSTEM_PORT:-$(default_system_port "$UDID")}}"
MODE="${4:-appium}"
APPIUM_URL="${APPIUM_SERVER_URL:-http://127.0.0.1:4723}"
DOUYIN_PACKAGE="${DOUYIN_PACKAGE_NAME:-com.ss.android.ugc.aweme}"

if [[ "$MODE" == "--adb-only" || "$MODE" == "adb" ]]; then
  adb -s "$UDID" shell monkey -p "$DOUYIN_PACKAGE" -c android.intent.category.LAUNCHER 1
  exit 0
fi

if ! adb devices | grep -q "$UDID[[:space:]]*device"; then
  echo "设备未在线：$UDID"
  echo "请先检查：adb devices"
  exit 1
fi

if ! curl -fsS "$APPIUM_URL/status" >/dev/null; then
  echo "Appium Server 未启动：$APPIUM_URL"
  echo "请先启动：appium --address 127.0.0.1 --port 4723"
  exit 1
fi

.venv/bin/python -m app.debug_open_douyin \
  --udid "$UDID" \
  --device-name "$DEVICE_NAME" \
  --system-port "$SYSTEM_PORT"
