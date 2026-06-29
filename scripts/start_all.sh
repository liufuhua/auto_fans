#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
PID_FILE="${START_ALL_PID_FILE:-$LOG_DIR/start_all.pids}"

export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export NO_COLOR="${NO_COLOR:-1}"
export FORCE_COLOR="${FORCE_COLOR:-0}"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-5173}"
APPIUM_HOST="${APPIUM_HOST:-127.0.0.1}"
APPIUM_PORT="${APPIUM_PORT:-4723}"
APPIUM_BIN="${APPIUM_BIN:-}"
APPIUM_LOG_LEVEL="${APPIUM_LOG_LEVEL:-info}"
ADB_PATH="${ADB_PATH:-adb}"
APPIUM_PORTS_FILE="${APPIUM_PORTS_FILE:-$LOG_DIR/appium_ports.txt}"
APPIUM_ON_DEMAND_FILE="${APPIUM_ON_DEMAND_FILE:-$LOG_DIR/appium_on_demand.txt}"
APPIUM_START_MODE="${APPIUM_START_MODE:-on_demand}"
APPIUM_BATCH_SIZE="${APPIUM_BATCH_SIZE:-2}"

SKIP_WEB="${SKIP_WEB:-0}"
SKIP_APPIUM="${SKIP_APPIUM:-0}"

LOCAL_NO_PROXY="localhost,127.0.0.1,::1,$API_HOST,$WEB_HOST,$APPIUM_HOST"
if [[ -n "${NO_PROXY:-}" ]]; then
  export NO_PROXY="$LOCAL_NO_PROXY,$NO_PROXY"
else
  export NO_PROXY="$LOCAL_NO_PROXY"
fi
if [[ -n "${no_proxy:-}" ]]; then
  export no_proxy="$LOCAL_NO_PROXY,$no_proxy"
else
  export no_proxy="$LOCAL_NO_PROXY"
fi

PIDS=()
NAMES=()
: >"$PID_FILE"
printf 'start_all %s\n' "$$" >>"$PID_FILE"

log() {
  printf '[start_all] %s\n' "$*"
}

find_executable() {
  local unix_path="$1"
  local windows_path="$2"

  if [[ -x "$unix_path" ]]; then
    printf '%s\n' "$unix_path"
    return 0
  fi

  if [[ -x "$windows_path" ]]; then
    printf '%s\n' "$windows_path"
    return 0
  fi

  return 1
}

find_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi
  return 1
}

is_windows_bash() {
  [[ "${OS:-}" == "Windows_NT" || "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]
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
    if [[ ! -f "$log_path" ]]; then
      printf '\xef\xbb\xbf' >"$log_path"
    fi
    exec >>"$log_path" 2>&1
    exec "$@"
  ) &

  local pid="$!"
  PIDS+=("$pid")
  NAMES+=("$name")
  printf '%s %s\n' "$name" "$pid" >>"$PID_FILE"
  log "$name pid=$pid log=$log_path"
}

wait_for_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"
  local timeout_seconds="${4:-60}"
  local started_at
  started_at="$(date +%s)"

  log "waiting for $name at $host:$port"
  while true; do
    if command -v powershell.exe >/dev/null 2>&1; then
      if powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
        "\$client = New-Object Net.Sockets.TcpClient; try { \$client.Connect('$host', $port); exit 0 } catch { exit 1 } finally { \$client.Close() }" \
        >/dev/null 2>&1; then
        log "$name is ready"
        return 0
      fi
    elif command -v nc >/dev/null 2>&1; then
      if nc -z "$host" "$port" >/dev/null 2>&1; then
        log "$name is ready"
        return 0
      fi
    fi

    if (( $(date +%s) - started_at >= timeout_seconds )); then
      log "$name did not become ready within ${timeout_seconds}s"
      return 1
    fi
    sleep 1
  done
}

load_appium_ports() {
  local configs_url="http://$API_HOST:$API_PORT/api/automation/devices/configs"
  local ports

  log "loading Appium ports from $configs_url" >&2
  if ! ports="$("$API_PYTHON_BIN" -c '
import json
import sys
import urllib.request
from urllib.parse import urlparse

configs_url = sys.argv[1]
fallback_port = int(sys.argv[2])
try:
    with urllib.request.urlopen(configs_url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    print(fallback_port)
    print(f"warning: failed to load device configs: {exc}", file=sys.stderr)
    raise SystemExit(0)

if isinstance(payload, dict):
    items = payload.get("data", payload)
elif isinstance(payload, list):
    items = payload
else:
    items = []

seen = set()
ports = []
for item in items:
    if not isinstance(item, dict):
        continue
    if item.get("enabledStatus") != "enabled":
        continue
    appium_url = item.get("appiumServerUrl") or ""
    parsed = urlparse(str(appium_url))
    if parsed.hostname not in ("127.0.0.1", "localhost", None, ""):
        device_name = item.get("name")
        print(
            f"warning: ignoring non-local Appium URL for {device_name}: {appium_url}",
            file=sys.stderr,
        )
        continue
    port = parsed.port
    if port is None:
        continue
    if port in seen:
        continue
    seen.add(port)
    ports.append(port)

if not ports:
    ports = [fallback_port]

for port in sorted(ports):
    print(port)
' "$configs_url" "$APPIUM_PORT" 2> >(while IFS= read -r line; do log "$line" >&2; done))"; then
    ports="$APPIUM_PORT"
  fi

  printf '%s\n' "$ports" | sed '/^$/d'
}

start_appium_server() {
  local port="$1"
  local name="appium_$port"
  local log_prefix="appium-$port"

  if [[ -n "$APPIUM_BIN" ]]; then
    start_process \
      "$name" \
      "$ROOT_DIR/automation_client" \
      "$log_prefix" \
      "$APPIUM_BIN" --address "$APPIUM_HOST" --port "$port" --log-level "$APPIUM_LOG_LEVEL"
  elif APPIUM_FOUND="$(find_command appium)"; then
    start_process \
      "$name" \
      "$ROOT_DIR/automation_client" \
      "$log_prefix" \
      "$APPIUM_FOUND" --address "$APPIUM_HOST" --port "$port" --log-level "$APPIUM_LOG_LEVEL"
  elif APPIUM_CMD_FOUND="$(find_command appium.cmd)"; then
    start_process \
      "$name" \
      "$ROOT_DIR/automation_client" \
      "$log_prefix" \
      "$APPIUM_CMD_FOUND" --address "$APPIUM_HOST" --port "$port" --log-level "$APPIUM_LOG_LEVEL"
  elif is_windows_bash && command -v powershell.exe >/dev/null 2>&1; then
    start_process \
      "$name" \
      "$ROOT_DIR/automation_client" \
      "$log_prefix" \
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
        "appium.cmd --address '$APPIUM_HOST' --port '$port' --log-level '$APPIUM_LOG_LEVEL'"
  else
    log "missing appium command. Install with: npm install -g appium"
    exit 1
  fi
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
  rm -f "$PID_FILE"
}

trap cleanup EXIT INT TERM

if command -v pgrep >/dev/null 2>&1 \
  && pgrep -f "python.*-m app.main.*--api-base-url http://$API_HOST:$API_PORT/api" >/dev/null 2>&1; then
  log "automation_client is already running for http://$API_HOST:$API_PORT/api"
  log "stop the old automation_client process before starting another start_all.sh"
  exit 1
fi

API_PYTHON_BIN="$(
  find_executable "$ROOT_DIR/api/.venv/bin/python" "$ROOT_DIR/api/.venv/Scripts/python.exe"
)" || {
  log "missing api virtualenv python"
  exit 1
}

CLIENT_PYTHON_BIN="$(
  find_executable "$ROOT_DIR/automation_client/.venv/bin/python" "$ROOT_DIR/automation_client/.venv/Scripts/python.exe"
)" || {
  log "missing automation_client virtualenv python"
  exit 1
}

start_process \
  "api" \
  "$ROOT_DIR/api" \
  "api" \
  "$API_PYTHON_BIN" -m uvicorn app.main:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --reload

if [[ "$SKIP_WEB" != "1" ]]; then
  start_process \
    "web_admin" \
    "$ROOT_DIR/web_admin" \
    "web_admin" \
    npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT"
fi

wait_for_tcp "api" "$API_HOST" "$API_PORT" 60
CLIENT_APPIUM_ARGS=()
if [[ "$SKIP_APPIUM" != "1" && "$APPIUM_START_MODE" != "on_demand" ]]; then
  mapfile -t APPIUM_PORTS < <(load_appium_ports)
  : >"$APPIUM_PORTS_FILE"
  rm -f "$APPIUM_ON_DEMAND_FILE"
  for port in "${APPIUM_PORTS[@]}"; do
    printf '%s\n' "$port" >>"$APPIUM_PORTS_FILE"
    start_appium_server "$port"
  done
  for port in "${APPIUM_PORTS[@]}"; do
    wait_for_tcp "appium_$port" "$APPIUM_HOST" "$port" 60
  done
elif [[ "$SKIP_APPIUM" != "1" ]]; then
  : >"$APPIUM_PORTS_FILE"
  printf 'on_demand batch_size=%s\n' "$APPIUM_BATCH_SIZE" >"$APPIUM_ON_DEMAND_FILE"
  CLIENT_APPIUM_ARGS=(--manage-appium-servers --appium-batch-size "$APPIUM_BATCH_SIZE")
  log "Appium on-demand mode enabled: batchSize=$APPIUM_BATCH_SIZE"
fi

start_process \
  "automation_client" \
  "$ROOT_DIR/automation_client" \
  "automation_client" \
  "$CLIENT_PYTHON_BIN" -m app.main \
    --api-base-url "http://$API_HOST:$API_PORT/api" \
    --appium-server-url "http://$APPIUM_HOST:$APPIUM_PORT" \
    --adb-path "$ADB_PATH" \
    "${CLIENT_APPIUM_ARGS[@]}" \
    "$@"

log "started. web=http://$WEB_HOST:$WEB_PORT api=http://$API_HOST:$API_PORT/api"
if [[ "$SKIP_APPIUM" != "1" && "$APPIUM_START_MODE" != "on_demand" ]]; then
  log "appium ports: ${APPIUM_PORTS[*]}"
elif [[ "$SKIP_APPIUM" != "1" ]]; then
  log "appium mode: on-demand batchSize=$APPIUM_BATCH_SIZE"
fi
log "press Ctrl+C to stop all processes"

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
