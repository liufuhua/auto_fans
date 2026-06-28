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
    echo "请指定 UDID：scripts/collect_video_authors.sh <udid> <limit>"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

LIMIT="${2:-4}"
DEVICE_NAME="${DEFAULT_DEVICE_NAME:-$(default_device_name "$UDID")}"
SYSTEM_PORT="${DEFAULT_SYSTEM_PORT:-$(default_system_port "$UDID")}"

if ! adb devices | grep -q "$UDID[[:space:]]*device"; then
  echo "设备未在线：$UDID"
  echo "请先检查：adb devices"
  exit 1
fi

.venv/bin/python -m app.debug_collect_video_authors \
  --udid "$UDID" \
  --device-name "$DEVICE_NAME" \
  --system-port "$SYSTEM_PORT" \
  --limit "$LIMIT"
