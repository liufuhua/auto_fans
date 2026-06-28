from __future__ import annotations

import json
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.device import Device


DEFAULT_HOST = "127.0.0.1"
SERVICE_PORTS = {
    "api": 8000,
    "web": 5173,
    "appium": 4723,
}
APPIUM_PORTS_FILE = Path("logs") / "appium_ports.txt"
APPIUM_ON_DEMAND_FILE = Path("logs") / "appium_on_demand.txt"


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _check_port_service(
    *,
    name: str,
    host: str,
    port: int,
    device_name: str | None = None,
    udid: str | None = None,
) -> dict[str, object]:
    running = _is_port_open(host, port)
    return {
        "name": name,
        "status": "running" if running else "stopped",
        "host": host,
        "port": port,
        "pid": None,
        "detail": "",
        "device_name": device_name,
        "udid": udid,
    }


def _appium_servers_from_devices(db: Session | None) -> list[dict[str, object]]:
    if db is None:
        return []

    devices = db.scalars(
        select(Device)
        .where(Device.enabled_status == "enabled")
        .order_by(Device.name)
    ).all()
    servers: list[dict[str, object]] = []
    seen_ports: set[tuple[str, int]] = set()
    for device in devices:
        appium_url = (device.appium_server_url or "").strip()
        if not appium_url:
            continue
        parsed = urlparse(appium_url)
        host = parsed.hostname or DEFAULT_HOST
        port = parsed.port
        if port is None:
            continue
        key = (host, port)
        if key in seen_ports:
            continue
        seen_ports.add(key)
        servers.append(
            _check_port_service(
                name=f"appium_{port}",
                host=host,
                port=port,
                device_name=device.name,
                udid=device.udid,
            )
        )
    return servers


def _default_appium_servers() -> list[dict[str, object]]:
    return [
        _check_port_service(
            name="appium_4723",
            host=DEFAULT_HOST,
            port=SERVICE_PORTS["appium"],
        )
    ]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _appium_on_demand_enabled() -> bool:
    return (_project_root() / APPIUM_ON_DEMAND_FILE).exists()


def _active_appium_ports() -> list[int]:
    ports_path = _project_root() / APPIUM_PORTS_FILE
    if not ports_path.exists():
        return []
    ports: list[int] = []
    for raw_line in ports_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.isdigit():
            continue
        port = int(line)
        if port not in ports:
            ports.append(port)
    return sorted(ports)


def _appium_servers_from_active_ports() -> list[dict[str, object]]:
    return [
        _check_port_service(
            name=f"appium_{port}",
            host=DEFAULT_HOST,
            port=port,
        )
        for port in _active_appium_ports()
    ]


def _summarize_appium_servers(
    servers: list[dict[str, object]],
    *,
    on_demand: bool = False,
) -> dict[str, object]:
    running_count = sum(1 for item in servers if item.get("status") == "running")
    total_count = len(servers)
    all_running = (total_count > 0 and running_count == total_count) or on_demand
    detail = "on-demand" if on_demand and total_count == 0 else f"{running_count}/{total_count} running"
    return {
        "name": "appium",
        "status": "running" if all_running else "stopped",
        "host": DEFAULT_HOST,
        "port": None,
        "pid": None,
        "detail": detail,
        "device_name": None,
        "udid": None,
    }


def _find_windows_process(pattern: str) -> tuple[int | None, str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.CommandLine -like '{pattern}' "
            "-and $_.CommandLine -notlike '*Get-CimInstance Win32_Process*' "
            "-and $_.Name -notlike 'powershell*' }} | "
            "Select-Object -First 1 ProcessId,CommandLine | ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception as exc:
        return None, f"process check failed: {exc}"

    output = completed.stdout.strip()
    if not output:
        return None, ""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None, output
    if isinstance(data, list):
        data = data[0] if data else {}
    pid = data.get("ProcessId")
    command_line = data.get("CommandLine") or ""
    return int(pid) if pid else None, command_line


def _recent_client_log(max_age_seconds: int = 90) -> Path | None:
    project_root = _project_root()
    log_dir = project_root / "logs"
    if not log_dir.exists():
        return None
    candidates = sorted(
        log_dir.glob("automation_client-*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    latest = candidates[0]
    age = datetime.now().timestamp() - latest.stat().st_mtime
    return latest if age <= max_age_seconds else None


def get_service_status(db: Session | None = None) -> dict[str, object]:
    services: dict[str, dict[str, object]] = {}
    for name, port in SERVICE_PORTS.items():
        if name == "appium":
            continue
        running = _is_port_open(DEFAULT_HOST, port)
        services[name] = {
            "name": name,
            "status": "running" if running else "stopped",
            "host": DEFAULT_HOST,
            "port": port,
            "pid": None,
            "detail": "",
        }

    on_demand = _appium_on_demand_enabled()
    if on_demand:
        appium_servers = _appium_servers_from_active_ports()
    else:
        appium_servers = _appium_servers_from_devices(db) or _default_appium_servers()
    services["appium"] = _summarize_appium_servers(appium_servers, on_demand=on_demand)

    pid, detail = _find_windows_process("*automation_client*app.main*")
    if not pid:
        recent_log = _recent_client_log()
        if recent_log:
            pid = None
            detail = f"recent log activity: {recent_log}"
    services["client"] = {
        "name": "client",
        "status": "running" if pid or detail.startswith("recent log activity:") else "stopped",
        "host": None,
        "port": None,
        "pid": pid,
        "detail": detail,
    }

    return {
        "updated_at": datetime.now(),
        "services": services,
        "appium_servers": appium_servers,
    }
