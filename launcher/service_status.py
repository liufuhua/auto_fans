from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
def env_port(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value and raw_value.isdigit():
        return int(raw_value)
    return default


def default_ports() -> dict[str, int]:
    return {
        "api": env_port("API_PORT", 8000),
        "web": env_port("WEB_PORT", 5173),
        "appium": env_port("APPIUM_PORT", 4723),
    }
APPIUM_PORTS_FILE = Path("logs") / "appium_ports.txt"
APPIUM_ON_DEMAND_FILE = Path("logs") / "appium_on_demand.txt"


@dataclass(frozen=True)
class ServiceInfo:
    name: str
    status: str
    host: str | None = None
    port: int | None = None
    pid: int | None = None
    detail: str = ""


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def check_port_service(name: str, port: int, host: str = DEFAULT_HOST) -> ServiceInfo:
    running = is_port_open(host, port)
    return ServiceInfo(
        name=name,
        status="running" if running else "stopped",
        host=host,
        port=port,
    )


def load_appium_ports(root: Path | None = None) -> list[int]:
    project_root = root or Path.cwd()
    ports_path = project_root / APPIUM_PORTS_FILE
    ports: list[int] = []
    if ports_path.exists():
        for raw_line in ports_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line.isdigit():
                continue
            port = int(line)
            if port not in ports:
                ports.append(port)
    return sorted(ports) or [default_ports()["appium"]]


def appium_on_demand_enabled(root: Path | None = None) -> bool:
    project_root = root or Path.cwd()
    return (project_root / APPIUM_ON_DEMAND_FILE).exists()


def collect_appium_servers(root: Path | None = None) -> list[dict[str, object]]:
    if appium_on_demand_enabled(root):
        ports_path = (root or Path.cwd()) / APPIUM_PORTS_FILE
        if not ports_path.exists() or not ports_path.read_text(encoding="utf-8").strip():
            return []
    servers: list[dict[str, object]] = []
    for port in load_appium_ports(root):
        info = check_port_service(f"appium_{port}", port)
        servers.append(asdict(info))
    return servers


def summarize_appium_servers(
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
    }


def process_matches(
    *,
    name: str,
    command_line: str,
    required_substrings: tuple[str, ...],
    ignored_substrings: tuple[str, ...] = (),
) -> bool:
    if not command_line:
        return False
    lowered_command = command_line.lower()
    lowered_name = name.lower()
    if lowered_name.startswith(("powershell", "pwsh")):
        return False
    if any(item.lower() in lowered_command for item in ignored_substrings):
        return False
    return all(item.lower() in lowered_command for item in required_substrings)


def find_windows_process(required_substrings: tuple[str, ...]) -> tuple[int | None, str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
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
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        command_line = item.get("CommandLine") or ""
        if not process_matches(
            name=item.get("Name") or "",
            command_line=command_line,
            required_substrings=required_substrings,
            ignored_substrings=("Get-CimInstance Win32_Process", "service_status"),
        ):
            continue
        pid = item.get("ProcessId")
        return int(pid) if pid else None, command_line
    return None, ""


def recent_client_log(root: Path | None = None, max_age_seconds: int = 90) -> Path | None:
    project_root = root or Path.cwd()
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


def check_client_process(root: Path | None = None) -> ServiceInfo:
    pid, detail = find_windows_process(("automation_client", ".venv", "-m app.main"))
    return ServiceInfo(
        name="client",
        status="running" if pid else "stopped",
        pid=pid,
        detail=detail,
    )


def collect_status(root: Path | None = None) -> dict[str, object]:
    services = {
        name: asdict(check_port_service(name, port))
        for name, port in default_ports().items()
        if name != "appium"
    }
    on_demand = appium_on_demand_enabled(root)
    appium_servers = collect_appium_servers(root)
    services["appium"] = summarize_appium_servers(appium_servers, on_demand=on_demand)
    services["client"] = asdict(check_client_process(root))
    return {
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "services": services,
        "appiumServers": appium_servers,
    }


def all_required_running(status: dict[str, object]) -> bool:
    services = status.get("services", {})
    if not isinstance(services, dict):
        return False
    services_running = all(
        isinstance(info, dict) and info.get("status") == "running"
        for info in services.values()
    )
    appium_servers = status.get("appiumServers", [])
    if not isinstance(appium_servers, list):
        return False
    appium_running = bool(services.get("appium", {}).get("status") == "running") and all(
        isinstance(info, dict) and info.get("status") == "running"
        for info in appium_servers
    )
    return services_running and appium_running


def write_status_file(root: Path, status: dict[str, object]) -> Path:
    status_dir = root / "logs" / "launcher"
    status_dir.mkdir(parents=True, exist_ok=True)
    status_path = status_dir / "service_status.json"
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status_path


def format_status(status: dict[str, object]) -> str:
    services = status.get("services", {})
    appium_servers = status.get("appiumServers", [])
    lines = [f"Updated at: {status.get('updatedAt', '-')}"]
    if isinstance(services, dict):
        for name in ("api", "web", "appium", "client"):
            info = services.get(name, {})
            if not isinstance(info, dict):
                continue
            detail = ""
            if info.get("port"):
                detail = f" {info.get('host')}:{info.get('port')}"
            if info.get("pid"):
                detail = f" pid={info.get('pid')}"
            if info.get("detail") and not detail:
                detail = f" {info.get('detail')}"
            lines.append(f"{name:<7} {info.get('status', 'unknown')}{detail}")
    if isinstance(appium_servers, list):
        for item in appium_servers:
            if not isinstance(item, dict):
                continue
            detail = ""
            if item.get("port"):
                detail = f" {item.get('host')}:{item.get('port')}"
            lines.append(f"{item.get('name', 'appium'):<12} {item.get('status', 'unknown')}{detail}")
    return "\n".join(lines)
