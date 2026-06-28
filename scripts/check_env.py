#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def run(command: list[str], timeout: int = 8) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    return completed.returncode == 0, completed.stdout.strip()


def first_line(text: str) -> str:
    return text.splitlines()[0] if text else ""


def app_path(name: str) -> Path | None:
    for base in (Path("/Applications"), Path.home() / "Applications"):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def app_exists(name: str) -> bool:
    return app_path(name) is not None


def find_download(pattern: str) -> str:
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return ""
    matches = sorted(downloads.glob(pattern))
    return str(matches[0]) if matches else ""


def check_java() -> CheckResult:
    ok, out = run(["java", "-version"])
    return CheckResult("Java JDK", ok, first_line(out), "Install JDK 8 or newer.")


def check_python() -> CheckResult:
    ok, out = run(["python3", "--version"])
    return CheckResult("Python 3", ok, out, "Install Python 3.x.")


def check_node() -> CheckResult:
    node_ok, node_out = run(["node", "--version"])
    npm_ok, npm_out = run(["npm", "--version"])
    ok = node_ok and npm_ok
    npm_version = next((line for line in npm_out.splitlines() if line and not line.lower().startswith("npm warn")), npm_out)
    detail = f"node {node_out}; npm {npm_version}"
    return CheckResult("Node.js / npm", ok, detail, "Use Node ^14.17, ^16.13, or >=18; npm >=8.")


def check_adb() -> CheckResult:
    adb = shutil.which("adb") or str(Path.home() / "Library/Android/sdk/platform-tools/adb")
    ok, out = run([adb, "version"]) if adb else (False, "")
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    detail = f"{first_line(out)}; ANDROID_HOME={android_home or 'not set'}"
    return CheckResult("Android SDK / ADB", ok, detail, "Install Android SDK platform-tools and export ANDROID_HOME.")


def check_appium() -> CheckResult:
    appium = shutil.which("appium")
    if not appium:
        return CheckResult("Appium Server CLI", False, "not found", "Run: npm install -g appium")
    ok, out = run(["npm", "list", "-g", "appium", "--depth=0"], timeout=12)
    detail = first_line(out)
    for line in out.splitlines():
        if "appium@" in line:
            detail = line.strip()
            break
    return CheckResult("Appium Server CLI", ok, detail, "Run: npm install -g appium")


def check_uiautomator2() -> CheckResult:
    appium = shutil.which("appium")
    if not appium:
        return CheckResult("Appium UiAutomator2 driver", False, "appium not found", "Run: appium driver install uiautomator2")

    package_json = Path.home() / ".appium/node_modules/appium-uiautomator2-driver/package.json"
    if package_json.exists():
        ok, out = run(["node", "-p", f"require('{package_json}').version"])
        detail = f"appium-uiautomator2-driver@{out}" if ok and out else str(package_json)
        return CheckResult("Appium UiAutomator2 driver", True, detail)

    ok, out = run(["appium", "driver", "list", "--installed"], timeout=15)
    installed = "uiautomator2" in out.lower()
    return CheckResult("Appium UiAutomator2 driver", ok and installed, out or "not installed", "Run: appium driver install uiautomator2")


def check_apps() -> list[CheckResult]:
    mumu_installed = any(
        app_exists(name)
        for name in (
            "MuMuLauncher.app",
            "MuMuPlayer.app",
            "MuMu Player.app",
            "MuMuPlayer Pro.app",
            "MuMu Nebula.app",
        )
    )
    mumu_dmg = find_download("*MuMu*.dmg") or find_download("*mumu*.dmg")
    inspector_installed = any(
        app_exists(name)
        for name in (
            "Appium Inspector.app",
            "Appium Inspector GUI.app",
        )
    )
    vscode_installed = app_exists("Visual Studio Code.app")
    code_cli = shutil.which("code")
    return [
        CheckResult("MuMu emulator", mumu_installed, "installed" if mumu_installed else f"installer: {mumu_dmg or 'not found'}", "Install the downloaded MuMu DMG and enable ADB debugging."),
        CheckResult("Appium Inspector", inspector_installed, "installed" if inspector_installed else "not found in /Applications", "Download and install Appium Inspector."),
        CheckResult("VS Code", vscode_installed, f"app installed; code cli: {code_cli or 'not configured'}", "Install VS Code shell command from the Command Palette if needed."),
        CheckResult("Appium Server GUI", app_exists("Appium Server GUI.app"), "installed" if app_exists("Appium Server GUI.app") else "not found", "CLI Appium is enough for CI; GUI is optional."),
    ]


def main() -> int:
    checks = [
        check_java(),
        check_python(),
        check_node(),
        check_adb(),
        check_appium(),
        check_uiautomator2(),
        *check_apps(),
    ]

    width = max(len(item.name) for item in checks)
    failed = 0
    for item in checks:
        mark = "OK" if item.ok else "NO"
        print(f"[{mark}] {item.name:<{width}}  {item.detail}")
        if not item.ok:
            failed += 1
            if item.hint:
                print(f"     hint: {item.hint}")

    print()
    print(f"Checked project: {ROOT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
