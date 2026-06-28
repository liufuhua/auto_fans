from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_UDID = "W8HUKRGUCU5X89ON"
PACKAGES = (
    "io.appium.settings",
    "io.appium.uiautomator2.server",
    "io.appium.uiautomator2.server.test",
)


@dataclass(frozen=True)
class ApkTarget:
    label: str
    package_name: str
    relative_path: Path


APK_TARGETS = (
    ApkTarget(
        "Appium Settings",
        "io.appium.settings",
        Path("settings_apk-debug.apk"),
    ),
    ApkTarget(
        "UiAutomator2 Server",
        "io.appium.uiautomator2.server",
        Path("appium-uiautomator2-server-v10.1.0.apk"),
    ),
    ApkTarget(
        "UiAutomator2 Test",
        "io.appium.uiautomator2.server.test",
        Path("appium-uiautomator2-server-debug-androidTest.apk"),
    ),
)


def run(command: list[str], *, timeout: int = 120) -> tuple[bool, str]:
    print("+ " + " ".join(f'"{part}"' if " " in part else part for part in command))
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
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except FileNotFoundError:
        return False, f"command not found: {command[0]}"

    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return completed.returncode == 0, output


def find_adb(explicit: str | None) -> str:
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
        try:
            exists = candidate.exists()
        except OSError:
            exists = False
        if exists:
            return str(candidate)
    raise RuntimeError("adb not found. Use --adb to specify adb.exe")


def appium_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path.home() / ".appium"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def apk_path(home: Path, target: ApkTarget) -> Path:
    bundled_path = project_root() / "tools" / "appium-apks" / target.relative_path.name
    if bundled_path.exists():
        return bundled_path

    legacy_paths = [
        home / "node_modules/appium-uiautomator2-driver/node_modules/io.appium.settings/apks" / target.relative_path.name,
        home
        / "node_modules/appium-uiautomator2-driver/node_modules/appium-uiautomator2-server/apks"
        / target.relative_path.name,
    ]
    for path in legacy_paths:
        if path.exists():
            return path

    matches = list(home.rglob(target.relative_path.name))
    if matches:
        return matches[0]
    raise RuntimeError(f"{target.label} apk not found: {bundled_path}")


def adb(adb_path: str, udid: str, *args: str, timeout: int = 120) -> tuple[bool, str]:
    return run([adb_path, "-s", udid, *args], timeout=timeout)


def package_installed(adb_path: str, udid: str, package_name: str) -> bool:
    ok, output = adb(adb_path, udid, "shell", "pm", "path", package_name, timeout=30)
    return ok and "package:" in output


def install_apk(adb_path: str, udid: str, path: Path, *, timeout: int) -> None:
    ok, output = adb(
        adb_path,
        udid,
        "install",
        "-r",
        "--no-incremental",
        str(path),
        timeout=timeout,
    )
    if not ok:
        raise RuntimeError(output)
    print(output or "install ok")


def verify_instrumentation(adb_path: str, udid: str) -> None:
    ok, output = adb(adb_path, udid, "shell", "pm", "list", "instrumentation", timeout=30)
    needle = "io.appium.uiautomator2.server.test"
    if not ok or needle not in output:
        raise RuntimeError(f"UiAutomator2 instrumentation not found:\n{output}")
    print("instrumentation ok")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Appium Settings and UiAutomator2 server/test apks to one Android device."
    )
    parser.add_argument("--udid", default=DEFAULT_UDID)
    parser.add_argument("--adb", help="Path to adb.exe")
    parser.add_argument("--appium-home", help="Path to .appium directory")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--skip-installed", action="store_true")
    args = parser.parse_args()

    adb_path = find_adb(args.adb)
    home = appium_home(args.appium_home)

    ok, output = adb(adb_path, args.udid, "get-state", timeout=15)
    if not ok or output.strip() != "device":
        raise RuntimeError(f"device not ready: {args.udid}, output={output!r}")
    print(f"device ok: {args.udid}")

    resolved = [(target, apk_path(home, target)) for target in APK_TARGETS]
    for target, path in resolved:
        if args.skip_installed and package_installed(adb_path, args.udid, target.package_name):
            print(f"[SKIP] {target.label}: {target.package_name} already installed")
            continue
        print(f"[INSTALL] {target.label}: {path}")
        install_apk(adb_path, args.udid, path, timeout=args.timeout)

    for package_name in PACKAGES:
        installed = package_installed(adb_path, args.udid, package_name)
        print(f"[{'PASS' if installed else 'FAIL'}] {package_name}")
        if not installed:
            return 1

    verify_instrumentation(adb_path, args.udid)
    print("Appium device packages are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
