#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

API_BASE_URL="${API_BASE_URL:-https://android-auto-api.rinal-li.cn/api}"
APPIUM_HOST="${APPIUM_HOST:-127.0.0.1}"
APPIUM_PORT="${APPIUM_PORT:-4723}"
APPIUM_SERVER_URL="${APPIUM_SERVER_URL:-http://$APPIUM_HOST:$APPIUM_PORT}"
APPIUM_BIN="${APPIUM_BIN:-appium}"
APPIUM_LOG_LEVEL="${APPIUM_LOG_LEVEL:-info}"
SKIP_APPIUM="${SKIP_APPIUM:-0}"

PIDS=()
NAMES=()

log() {
  printf '[start_client_remote_api] %s\n' "$*"
}

start_process() {
  local name="$1"
  local workdir="$2"
  local log_prefix="$3"
  local local_date
  local_date="$(date '+%F')"
  local log_path="$LOG_DIR/$log_prefix-$local_date.txt"
  shift 3

  log "starting $name"
  (
    cd "$workdir"
    exec >>"$log_path" 2>&1
    exec "$@"
  ) &

  local pid="$!"
  PIDS+=("$pid")
  NAMES+=("$name")
  log "$name pid=$pid log=$log_path"
}

cleanup() {
  if ((${#PIDS[@]} == 0)); then
    return
  fi

  log "stopping child processes"
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

if [[ ! -x "$ROOT_DIR/automation_client/.venv/bin/python" ]]; then
  log "missing automation_client/.venv/bin/python"
  exit 1
fi

if pgrep -f "python.*-m app.main.*--api-base-url $API_BASE_URL" >/dev/null 2>&1; then
  log "automation_client is already running for $API_BASE_URL"
  log "stop the old automation_client process before starting another one"
  exit 1
fi

if [[ "$SKIP_APPIUM" != "1" ]]; then
  start_process \
    "appium" \
    "$ROOT_DIR/automation_client" \
    "appium" \
    "$APPIUM_BIN" --address "$APPIUM_HOST" --port "$APPIUM_PORT" --log-level "$APPIUM_LOG_LEVEL"
fi

start_process \
  "automation_client" \
  "$ROOT_DIR/automation_client" \
  "automation_client" \
  "$ROOT_DIR/automation_client/.venv/bin/python" -m app.main \
    --api-base-url "$API_BASE_URL" \
    --appium-server-url "$APPIUM_SERVER_URL" \
    "$@"

log "started. api=$API_BASE_URL appium=$APPIUM_SERVER_URL"
log "press Ctrl+C to stop local automation_client and Appium"

while true; do
  for index in "${!PIDS[@]}"; do
    pid="${PIDS[$index]}"
    name="${NAMES[$index]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      log "$name exited; stopping all"
      exit 1
    fi
  done
  sleep 2
done
