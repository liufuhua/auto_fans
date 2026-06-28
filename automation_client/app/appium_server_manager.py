from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.device_manager import BackendDeviceConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppiumServerSpec:
    host: str
    port: int
    url: str


class AppiumServerManager:
    """Starts and stops local Appium servers for active device batches."""

    def __init__(
        self,
        *,
        default_server_url: str,
        log_dir: str | Path = "../logs",
        ports_file: str | Path = "../logs/appium_ports.txt",
        on_demand_file: str | Path = "../logs/appium_on_demand.txt",
        appium_bin: str | None = None,
        log_level: str = "info",
    ) -> None:
        self.default_server_url = default_server_url
        self.log_dir = Path(log_dir)
        self.ports_file = Path(ports_file)
        self.on_demand_file = Path(on_demand_file)
        self.appium_bin = appium_bin or os.environ.get("APPIUM_BIN") or ""
        self.log_level = os.environ.get("APPIUM_LOG_LEVEL") or log_level
        self._processes: dict[int, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()
        self._write_on_demand_file()

    def start_for_devices(self, devices: list[BackendDeviceConfig]) -> list[AppiumServerSpec]:
        specs = self._specs_for_devices(devices)
        with self._lock:
            try:
                for spec in specs:
                    if self._is_running(spec.port):
                        continue
                    self._clear_port_before_start_locked(spec.port)
                    self._processes[spec.port] = self._start_process(spec)
                for spec in specs:
                    self._wait_for_server_locked(spec)
            except Exception:
                logger.exception("failed to start Appium servers for batch")
                for spec in specs:
                    self._stop_port_locked(spec.port)
                raise
            finally:
                self._write_ports_file_locked()
        return specs

    def stop_for_devices(self, devices: list[BackendDeviceConfig]) -> None:
        specs = self._specs_for_devices(devices)
        with self._lock:
            for spec in specs:
                self._stop_port_locked(spec.port)
            self._write_ports_file_locked()

    def stop_all(self) -> None:
        with self._lock:
            for port in list(self._processes):
                self._stop_port_locked(port)
            self._write_ports_file_locked()

    def _specs_for_devices(self, devices: list[BackendDeviceConfig]) -> list[AppiumServerSpec]:
        specs: dict[int, AppiumServerSpec] = {}
        for device in devices:
            spec = self._spec_from_url(device.appium_server_url or self.default_server_url)
            if spec.port not in specs:
                specs[spec.port] = spec
        return sorted(specs.values(), key=lambda item: item.port)

    @staticmethod
    def _spec_from_url(url: str) -> AppiumServerSpec:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        if host not in {"127.0.0.1", "localhost"}:
            raise RuntimeError(f"Only local Appium servers can be managed: {url}")
        port = parsed.port
        if port is None:
            raise RuntimeError(f"Appium server URL is missing a port: {url}")
        return AppiumServerSpec(host=host, port=port, url=f"http://{host}:{port}")

    def _is_running(self, port: int) -> bool:
        process = self._processes.get(port)
        return process is not None and process.poll() is None

    def _start_process(self, spec: AppiumServerSpec) -> subprocess.Popen[str]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command(spec)
        logger.info("starting Appium server: url=%s command=%s", spec.url, command)
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=isinstance(command, str),
            env=_appium_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return process

    def _wait_for_server_locked(self, spec: AppiumServerSpec, timeout_seconds: float = 30) -> None:
        deadline = time.monotonic() + timeout_seconds
        process = self._processes.get(spec.port)
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise RuntimeError(
                    f"Appium server exited before ready: url={spec.url} exitCode={process.returncode}"
                )
            if _is_tcp_open(spec.host, spec.port):
                logger.info("Appium server is ready: url=%s", spec.url)
                return
            time.sleep(0.5)
        raise RuntimeError(f"Appium server did not become ready within {timeout_seconds}s: {spec.url}")

    def _build_command(self, spec: AppiumServerSpec) -> list[str] | str:
        args = [
            "--address",
            spec.host,
            "--port",
            str(spec.port),
            "--log-level",
            self.log_level,
            "--log-no-colors",
        ]
        if self.appium_bin:
            return _wrap_windows_command_if_needed(self.appium_bin, args)
        appium = shutil.which("appium")
        if appium:
            return _wrap_windows_command_if_needed(appium, args)
        appium_cmd = shutil.which("appium.cmd")
        if appium_cmd:
            return _wrap_windows_command_if_needed(appium_cmd, args)
        if sys.platform == "win32":
            command_text = " ".join(["appium.cmd", *(_quote_arg(arg) for arg in args)])
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command_text,
            ]
        raise RuntimeError("missing appium command. Install with: npm install -g appium")

    def _stop_port_locked(self, port: int) -> None:
        process = self._processes.pop(port, None)
        if process is not None and process.poll() is None:
            logger.info("stopping Appium server: port=%s pid=%s", port, process.pid)
            _terminate_process_tree(process)
        self._stop_stale_processes_on_port_locked(port)
        self._wait_for_port_closed_locked(port)

    def _clear_port_before_start_locked(self, port: int) -> None:
        if not _is_tcp_open("127.0.0.1", port):
            return
        logger.warning("Appium port is already in use before start; clearing stale process: port=%s", port)
        self._stop_stale_processes_on_port_locked(port)
        self._wait_for_port_closed_locked(port)
        if _is_tcp_open("127.0.0.1", port):
            raise RuntimeError(f"Appium port is still in use after cleanup: port={port}")

    def _stop_stale_processes_on_port_locked(self, port: int) -> None:
        for pid in _list_listening_pids(port):
            logger.warning("stopping process listening on Appium port: port=%s pid=%s", port, pid)
            _kill_pid_tree(pid)

    @staticmethod
    def _wait_for_port_closed_locked(port: int, timeout_seconds: float = 5) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not _is_tcp_open("127.0.0.1", port):
                return
            time.sleep(0.2)

    def _write_ports_file_locked(self) -> None:
        self.ports_file.parent.mkdir(parents=True, exist_ok=True)
        active_ports = [
            port
            for port, process in sorted(self._processes.items())
            if process.poll() is None
        ]
        self.ports_file.write_text(
            "".join(f"{port}\n" for port in active_ports),
            encoding="utf-8",
        )

    def _write_on_demand_file(self) -> None:
        self.on_demand_file.parent.mkdir(parents=True, exist_ok=True)
        self.on_demand_file.write_text(
            "on_demand managed_by=automation_client\n",
            encoding="utf-8",
        )


def _quote_arg(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", value):
        return value
    return "'" + value.replace("'", "''") + "'"


def _wrap_windows_command_if_needed(command: str, args: list[str]) -> list[str] | str:
    suffix = Path(command).suffix.lower()
    if sys.platform != "win32" or suffix not in {".cmd", ".bat"}:
        return [command, *args]
    command_text = " ".join([_cmd_quote_arg(command), *(_cmd_quote_arg(arg) for arg in args)])
    return command_text


def _cmd_quote_arg(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def _appium_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    return env


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        _kill_pid_tree(process.pid)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _kill_pid_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
        return
    try:
        os.kill(pid, 15)
    except OSError:
        return


def _list_listening_pids(port: int) -> list[int]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except OSError:
        return []

    pids: set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address = parts[1]
        state = parts[3].upper()
        if state != "LISTENING" or not local_address.endswith(f":{port}"):
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(pids)


def _is_tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0
