#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

detect_udid() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

detect_screen_width() {
  adb -s "$1" shell wm size | awk -F '[: x]+' '/Physical size/ {print $3}'
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
MODE="${4:-${TAP_SEARCH_MODE:-appium}}"
if [[ -z "$UDID" ]]; then
  ONLINE_UDIDS="$(detect_udid)"
  ONLINE_COUNT="$(printf "%s\n" "$ONLINE_UDIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$ONLINE_COUNT" != "1" ]]; then
    echo "未指定设备，且当前在线设备数量不是 1。"
    echo "请指定 UDID：scripts/tap_search.sh <udid> <x> <y>"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

if [[ -n "${2:-}" ]]; then
  X="$2"
elif [[ -n "${SEARCH_TAP_X:-}" ]]; then
  X="$SEARCH_TAP_X"
else
  SCREEN_WIDTH="$(detect_screen_width "$UDID")"
  X="$((SCREEN_WIDTH - 90))"
fi
Y="${3:-${SEARCH_TAP_Y:-196}}"
SEARCH_XPATH="${SEARCH_XPATH:-//android.widget.Button[@resource-id=\"com.ss.android.ugc.aweme:id/2ei\"]}"

if ! adb devices | grep -q "$UDID[[:space:]]*device"; then
  echo "设备未在线：$UDID"
  echo "请先检查：adb devices"
  exit 1
fi

if [[ "$MODE" != "--adb-only" && "$MODE" != "adb" ]]; then
  DEVICE_NAME="${DEFAULT_DEVICE_NAME:-$(default_device_name "$UDID")}"
  SYSTEM_PORT="${DEFAULT_SYSTEM_PORT:-$(default_system_port "$UDID")}"
  if .venv/bin/python -m app.debug_tap_search \
    --udid "$UDID" \
    --device-name "$DEVICE_NAME" \
    --system-port "$SYSTEM_PORT" \
    --xpath "$SEARCH_XPATH" \
    --fallback-x "$X" \
    --fallback-y "$Y"; then
    exit 0
  fi
  echo "Appium XPath 点击失败，回退到 ADB 坐标点击：x=$X y=$Y"
fi

adb -s "$UDID" shell input tap "$X" "$Y"
echo "tapped search: udid=$UDID x=$X y=$Y"
