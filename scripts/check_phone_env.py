from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DOUYIN_PACKAGE = "com.ss.android.ugc.aweme"
APPIUM_PACKAGES = [
    "io.appium.settings",
    "io.appium.uiautomator2.server",
    "io.appium.uiautomator2.server.test",
]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    suggestion: str = ""


def run(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s: {' '.join(command)}"

    output = "\n".join(
        part.strip() for part in [completed.stdout, completed.stderr] if part.strip()
    )
    return completed.returncode == 0, output


def find_adb(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    return None


def parse_adb_devices(output: str) -> dict[str, str]:
    devices: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices[parts[0]] = parts[1]
    return devices


def choose_udid(adb: str, requested_udid: str | None) -> tuple[str | None, Check]:
    ok, output = run([adb, "devices"], timeout=15)
    if not ok:
        return None, Check("ADB devices", False, output, "检查 adb 是否在 PATH 中，并确认手机授权")

    devices = parse_adb_devices(output)
    if requested_udid:
        state = devices.get(requested_udid)
        if state is None:
            return requested_udid, Check(
                "ADB device",
                False,
                f"{requested_udid} not found. connected={devices}",
                "确认 USB 连接、手机授权、UDID 是否正确",
            )
        return requested_udid, Check(
            "ADB device",
            state == "device",
            f"{requested_udid} state={state}",
            "手机需要显示为 device，不能是 offline/unauthorized",
        )

    online = [udid for udid, state in devices.items() if state == "device"]
    if len(online) == 1:
        return online[0], Check("ADB device", True, f"{online[0]} state=device")
    if not online:
        return None, Check(
            "ADB device",
            False,
            f"no online device. connected={devices}",
            "连接一台手机并在手机上允许 USB 调试授权",
        )
    return None, Check(
        "ADB device",
        False,
        f"multiple online devices: {online}",
        "请使用 --udid 指定要检测的手机",
    )


def adb_shell(adb: str, udid: str, command: str, timeout: int = 20) -> tuple[bool, str]:
    return run([adb, "-s", udid, "shell", command], timeout=timeout)


def get_prop(adb: str, udid: str, prop: str) -> str:
    ok, output = adb_shell(adb, udid, f"getprop {prop}", timeout=10)
    return output.strip() if ok else ""


def package_info(adb: str, udid: str, package_name: str) -> tuple[bool, str]:
    ok, output = adb_shell(adb, udid, f"dumpsys package {package_name}", timeout=20)
    if not ok:
        return False, output or "dumpsys package failed"
    if "Unable to find package" in output or not output.strip():
        return False, "not installed"

    version_name = ""
    version_code = ""
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("versionName="):
            version_name = text.split("=", 1)[1]
        elif "versionCode=" in text and not version_code:
            version_code = text
    detail = ", ".join(part for part in [version_name, version_code] if part)
    return True, detail or "installed"


def check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_appium_status(server_url: str) -> Check:
    normalized = server_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{normalized}/status", timeout=4) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return Check(
            "Appium server",
            False,
            f"{server_url} not reachable: {exc}",
            "先启动 Appium 服务，默认端口是 4723",
        )

    try:
        data = json.loads(body)
        value = data.get("value", data)
        version = value.get("build", {}).get("version") or value.get("version") or "unknown"
        return Check("Appium server", True, f"{server_url} version={version}")
    except json.JSONDecodeError:
        return Check("Appium server", True, f"{server_url} responded: {body[:120]}")


def check_appium_cli() -> Check:
    appium = shutil.which("appium") or shutil.which("appium.cmd")
    if not appium:
        return Check("Appium CLI", False, "not found", "运行 npm install -g appium")
    ok, output = run([appium, "driver", "list", "--installed"], timeout=20)
    has_uiautomator2 = "uiautomator2" in output.lower()
    return Check(
        "UiAutomator2 driver",
        ok and has_uiautomator2,
        output or appium,
        "运行 appium driver install uiautomator2",
    )


def check_port_free(port: int) -> Check:
    in_use = check_tcp("127.0.0.1", port)
    return Check(
        f"systemPort {port}",
        not in_use,
        "free" if not in_use else "already listening on 127.0.0.1",
        "确认没有残留的 Appium 转发或其他进程占用该端口",
    )


def print_report(checks: list[Check]) -> None:
    width = max(len(check.name) for check in checks)
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"[{status}] {check.name.ljust(width)}  {check.detail}")
        if not check.ok and check.suggestion:
            print(f"       suggestion: {check.suggestion}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a connected Android phone is ready for this Appium project."
    )
    parser.add_argument("--udid", help="ADB device UDID. If omitted, use the only online device.")
    parser.add_argument("--adb", help="Path to adb.exe")
    parser.add_argument("--system-port", type=int, default=8206)
    parser.add_argument("--appium-server-url", default="http://127.0.0.1:4723")
    parser.add_argument("--douyin-package", default=DEFAULT_DOUYIN_PACKAGE)
    args = parser.parse_args()

    checks: list[Check] = []

    adb = find_adb(args.adb)
    checks.append(
        Check(
            "ADB binary",
            adb is not None,
            adb or "not found",
            "安装 Android SDK platform-tools，或使用 --adb 指定 adb.exe",
        )
    )
    if adb is None:
        print_report(checks)
        return 1

    udid, device_check = choose_udid(adb, args.udid)
    checks.append(device_check)
    if not udid or not device_check.ok:
        print_report(checks)
        return 1

    model = get_prop(adb, udid, "ro.product.model")
    android_version = get_prop(adb, udid, "ro.build.version.release")
    sdk = get_prop(adb, udid, "ro.build.version.sdk")
    checks.append(Check("Android version", bool(sdk), f"model={model}, android={android_version}, sdk={sdk}"))

    ok, output = adb_shell(adb, udid, "settings get global hidden_api_policy", timeout=10)
    checks.append(Check("ADB shell", ok, output if output else "shell command ok", "确认 USB 调试已授权"))

    for package_name in [args.douyin_package, *APPIUM_PACKAGES]:
        installed, detail = package_info(adb, udid, package_name)
        suggestion = ""
        if package_name.startswith("io.appium.uiautomator2"):
            suggestion = "这个包缺失时 Appium 每次启动都会尝试重新安装"
        elif package_name == "io.appium.settings":
            suggestion = "Appium Settings 缺失时首次启动会自动安装"
        elif package_name == args.douyin_package:
            suggestion = "请先在手机上安装抖音"
        checks.append(Check(f"Package {package_name}", installed, detail, suggestion))

    ok, output = adb_shell(
        adb,
        udid,
        "pm list instrumentation | grep io.appium.uiautomator2.server.test",
        timeout=15,
    )
    checks.append(
        Check(
            "UiAutomator2 instrumentation",
            ok and bool(output.strip()),
            output.strip() or "not found",
            "通常表示 server.test 没有安装完整",
        )
    )

    checks.append(check_appium_cli())
    checks.append(check_appium_status(args.appium_server_url))
    checks.append(check_port_free(args.system_port))

    print_report(checks)
    failed = [check for check in checks if not check.ok]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)} failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
