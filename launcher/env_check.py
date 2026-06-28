from __future__ import annotations

import os
import shutil
import socket
import ctypes
import subprocess
from dataclasses import dataclass
from pathlib import Path


REQUIRED_PROJECT_PATHS = [
    "api",
    "web_admin",
    "automation_client",
    "scripts/start_all.ps1",
    "scripts/finish_all.ps1",
]

REQUIRED_COMMANDS = [
    (("python", "py"), "Python"),
    (("node",), "Node.js"),
    (("npm",), "npm"),
    (("adb",), "ADB"),
    (("appium", "appium.cmd"), "Appium"),
    (("mysql",), "MySQL client"),
    (("powershell", "powershell.exe"), "PowerShell"),
]

GIT_BASH_CANDIDATES = [
    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    Path(r"C:\Program Files\Git\bin\bash.exe"),
]

DEFAULT_PORTS = {
    "api": 8000,
    "web": 5173,
    "appium": 4723,
}


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def find_project_root(start: Path | None = None) -> Path:
    root = (start or Path.cwd()).resolve()
    if root.is_file():
        root = root.parent
    return root


def find_git_bash() -> str | None:
    for candidate in GIT_BASH_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return shutil.which("bash.exe") or shutil.which("bash")


def extra_path_entries() -> list[str]:
    entries: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    program_files = os.environ.get("ProgramFiles")

    candidates = []
    if local_app_data:
        candidates.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools")
    if app_data:
        candidates.append(Path(app_data) / "npm")
    if program_files:
        candidates.append(Path(program_files) / "nodejs")

    for candidate in candidates:
        entries.append(str(candidate))
    return entries


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    entries = extra_path_entries()
    if entries:
        env["PATH"] = os.pathsep.join(entries + [env.get("PATH", "")])
    return env


def find_command(commands: tuple[str, ...]) -> str | None:
    search_path = os.pathsep.join(extra_path_entries() + [os.environ.get("PATH", "")])
    for command in commands:
        found = shutil.which(command, path=search_path)
        if found:
            return found
        for candidate in command_candidates(command):
            if path_exists(candidate):
                return str(candidate)
    return None


def command_candidates(command: str) -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    candidates: list[Path] = []
    if command == "adb" and local_app_data:
        candidates.append(Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    if command in {"appium", "appium.cmd"} and app_data:
        candidates.append(Path(app_data) / "npm" / "appium.cmd")
    return candidates


def path_exists(path: Path) -> bool:
    try:
        if path.exists():
            return True
    except OSError:
        pass

    escaped_path = str(path).replace("'", "''")
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"if (Test-Path -LiteralPath '{escaped_path}') {{ exit 0 }} else {{ exit 1 }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return completed.returncode == 0
    except Exception:
        return False


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def check_project_root(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_PROJECT_PATHS:
        if not (root / relative).exists():
            errors.append(f"Missing project path: {relative}")
    return errors


def check_commands() -> list[str]:
    errors: list[str] = []
    for commands, display_name in REQUIRED_COMMANDS:
        if not find_command(commands):
            joined = " or ".join(commands)
            errors.append(f"{display_name} is not available in PATH: {joined}")
    if not find_git_bash():
        errors.append("Git Bash is not installed or not available in PATH")
    return errors


def check_ports_available(host: str = "127.0.0.1") -> list[str]:
    warnings: list[str] = []
    for name, port in DEFAULT_PORTS.items():
        if is_port_open(host, port):
            warnings.append(f"Port already listening before start: {name} {host}:{port}")
    return warnings


def run_environment_check(root: Path | None = None) -> CheckResult:
    project_root = find_project_root(root)
    errors = []
    warnings = []

    errors.extend(check_project_root(project_root))
    errors.extend(check_commands())
    warnings.extend(check_ports_available())

    return CheckResult(ok=not errors, errors=errors, warnings=warnings)


def show_error_popup(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000010)
    except Exception:
        print(f"{title}\n{message}")


def format_check_result(result: CheckResult) -> str:
    lines: list[str] = []
    if result.errors:
        lines.append("Environment check failed:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        if lines:
            lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in result.warnings)
    if not lines:
        lines.append("Environment check passed.")
    return os.linesep.join(lines)
