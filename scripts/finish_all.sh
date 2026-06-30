#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="${START_ALL_PID_FILE:-$LOG_DIR/start_all.pids}"
ENV_FILE="${START_ALL_ENV_FILE:-$LOG_DIR/start_all.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
APPIUM_PORT="${APPIUM_PORT:-4723}"
APPIUM_ON_DEMAND_PORT_RANGE="${APPIUM_ON_DEMAND_PORT_RANGE:-4721-4730}"
API_HOST="${API_HOST:-127.0.0.1}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
APPIUM_HOST="${APPIUM_HOST:-127.0.0.1}"
APPIUM_PORTS_FILE="${APPIUM_PORTS_FILE:-$LOG_DIR/appium_ports.txt}"
APPIUM_ON_DEMAND_FILE="${APPIUM_ON_DEMAND_FILE:-$LOG_DIR/appium_on_demand.txt}"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

log() {
  printf '[finish_all] %s\n' "$*"
}

run_or_print() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[finish_all] dry-run: %s\n' "$*"
    return 0
  fi
  "$@"
}

load_appium_ports() {
  local ports=()
  local line
  if [[ -f "$APPIUM_PORTS_FILE" ]]; then
    while IFS= read -r line; do
      [[ "$line" =~ ^[0-9]+$ ]] || continue
      ports+=("$line")
    done <"$APPIUM_PORTS_FILE"
  fi

  if [[ -f "$APPIUM_ON_DEMAND_FILE" ]]; then
    local range_start="${APPIUM_ON_DEMAND_PORT_RANGE%-*}"
    local range_end="${APPIUM_ON_DEMAND_PORT_RANGE#*-}"
    if [[ "$range_start" =~ ^[0-9]+$ && "$range_end" =~ ^[0-9]+$ && "$range_start" -le "$range_end" ]]; then
      local port
      for ((port = range_start; port <= range_end; port++)); do
        ports+=("$port")
      done
    fi
  fi

  if ((${#ports[@]} == 0)); then
    ports+=("$APPIUM_PORT")
  fi

  printf '%s\n' "${ports[@]}" | sort -n -u
}

joined_appium_ports() {
  local ports=("$@")
  local joined=""
  local port
  for port in "${ports[@]}"; do
    if [[ -z "$joined" ]]; then
      joined="$port"
    else
      joined="$joined,$port"
    fi
  done
  printf '%s\n' "$joined"
}

stop_pid() {
  local name="$1"
  local pid="$2"

  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    return 0
  fi

  if kill -0 "$pid" 2>/dev/null; then
    log "stopping $name pid=$pid"
    run_or_print kill "$pid" 2>/dev/null || true
  else
    log "$name pid=$pid is not running"
  fi
}

force_stop_pid() {
  local name="$1"
  local pid="$2"

  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    return 0
  fi

  if kill -0 "$pid" 2>/dev/null; then
    log "force stopping $name pid=$pid"
    run_or_print kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_pid_file_processes() {
  if [[ ! -f "$PID_FILE" ]]; then
    log "pid file not found: $PID_FILE"
    return 0
  fi

  log "using pid file: $PID_FILE"
  while read -r name pid _rest; do
    stop_pid "$name" "$pid"
  done <"$PID_FILE"

  sleep 1

  while read -r name pid _rest; do
    force_stop_pid "$name" "$pid"
  done <"$PID_FILE"

  if [[ "$DRY_RUN" != "1" ]]; then
    rm -f "$PID_FILE"
  fi
}

remove_appium_ports_file() {
  if [[ "$DRY_RUN" != "1" ]]; then
    rm -f "$APPIUM_PORTS_FILE"
    rm -f "$APPIUM_ON_DEMAND_FILE"
    rm -f "$ENV_FILE"
  fi
}

stop_windows_ports() {
  if ! command -v powershell.exe >/dev/null 2>&1; then
    return 0
  fi

  mapfile -t appium_ports < <(load_appium_ports)
  local appium_ports_text
  appium_ports_text="$(joined_appium_ports "${appium_ports[@]}")"
  log "checking Windows ports: api=$API_HOST:$API_PORT web=$WEB_HOST:$WEB_PORT appium_ports=$appium_ports_text"
  API_PORT="$API_PORT" WEB_PORT="$WEB_PORT" APPIUM_PORTS="$appium_ports_text" DRY_RUN="$DRY_RUN" \
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
      $appiumPorts = @()
      if ($env:APPIUM_PORTS) {
        $appiumPorts = $env:APPIUM_PORTS -split "," | Where-Object { $_ }
      }
      $ports = @($env:API_PORT, $env:WEB_PORT) + $appiumPorts |
        Where-Object { $_ } |
        ForEach-Object { [int]$_ } |
        Sort-Object -Unique
      $seen = @{}
      foreach ($port in $ports) {
        $rows = @(netstat -ano | Select-String "LISTENING")
        foreach ($row in $rows) {
          $parts = ($row.ToString().Trim() -split "\s+")
          if ($parts.Count -lt 5) { continue }
          $localAddress = $parts[1]
          if (-not ($localAddress -match ":$port$")) { continue }
          $processId = [int]$parts[-1]
          if ($seen.ContainsKey($processId)) { continue }
          $seen[$processId] = $true
          $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
          $processName = if ($process) { $process.ProcessName } else { "unknown" }
          Write-Output "[finish_all] port $port owned by pid=$processId name=$processName"
          if ($env:DRY_RUN -ne "1") {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            taskkill /PID $processId /T /F 2>$null | Out-Null
          }
        }
      }
    ' || true
}

stop_windows_command_patterns() {
  if ! command -v powershell.exe >/dev/null 2>&1; then
    return 0
  fi

  log "checking Windows command lines for automation_client and appium"
  DRY_RUN="$DRY_RUN" powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
    $patterns = @(
      "*automation_client*app.main*",
      "*automation_client*win_test.py*",
      "*node*appium*index.js*--port*",
      "*appium.CMD*--port*"
    )
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        if ($cmd -like "*Get-CimInstance Win32_Process*") { return $false }
        foreach ($pattern in $patterns) {
          if ($cmd -like $pattern) { return $true }
        }
        return $false
      })
    foreach ($process in $processes) {
      Write-Output "[finish_all] command match pid=$($process.ProcessId) cmd=$($process.CommandLine)"
      if ($env:DRY_RUN -ne "1") {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
      }
    }
  ' || true
}

stop_unix_ports() {
  if command -v powershell.exe >/dev/null 2>&1; then
    return 0
  fi

  mapfile -t appium_ports < <(load_appium_ports)
  local ports=("$API_PORT" "$WEB_PORT" "${appium_ports[@]}")
  local port

  for port in "${ports[@]}"; do
    if command -v lsof >/dev/null 2>&1; then
      while read -r pid; do
        [[ -n "$pid" ]] || continue
        log "stopping process on port $port pid=$pid"
        run_or_print kill "$pid" 2>/dev/null || true
      done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
    elif command -v fuser >/dev/null 2>&1; then
      log "stopping processes on port $port via fuser"
      if [[ "$DRY_RUN" == "1" ]]; then
        fuser -n tcp "$port" 2>/dev/null || true
      else
        fuser -k -n tcp "$port" 2>/dev/null || true
      fi
    fi
  done
}

main() {
  log "finish requested"
  stop_pid_file_processes
  stop_windows_ports
  stop_windows_command_patterns
  stop_unix_ports
  remove_appium_ports_file
  log "finish complete"
}

main
