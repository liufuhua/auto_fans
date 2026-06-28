#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

detect_udid() {
  adb devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

UDID="${1:-${DEFAULT_UDID:-}}"
if [[ -z "$UDID" ]]; then
  ONLINE_UDIDS="$(detect_udid)"
  ONLINE_COUNT="$(printf "%s\n" "$ONLINE_UDIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$ONLINE_COUNT" != "1" ]]; then
    echo "未指定设备，且当前在线设备数量不是 1。"
    echo "用法：scripts/check_device_region.sh <udid>"
    adb devices
    exit 1
  fi
  UDID="$ONLINE_UDIDS"
fi

if ! adb devices | grep -q "$UDID[[:space:]]*device"; then
  echo "设备未在线：$UDID"
  echo "请先检查：adb devices"
  exit 1
fi

.venv/bin/python -m app.debug_device_region --udid "$UDID"
