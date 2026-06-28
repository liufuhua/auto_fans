from __future__ import annotations

import msvcrt
import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from env_check import build_runtime_env, format_check_result, run_environment_check, show_error_popup
from service_status import (
    all_required_running,
    collect_status,
    format_status,
    write_status_file,
)


MAX_RESTARTS = 3
MONITOR_INTERVAL_SECONDS = 5
STARTUP_GRACE_SECONDS = 30


class Launcher:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_dir = root / "logs" / "launcher"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"start_{stamp}.log"
        self.process: subprocess.Popen[str] | None = None
        self.restart_count = 0
        self.web_opened = False
        self.started_at = 0.0

    def log(self, message: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        try:
            print(line)
        except OSError:
            pass

    def run_checks(self) -> bool:
        self.log("Running environment check")
        result = run_environment_check(self.root)
        self.log(format_check_result(result))
        if not result.ok:
            show_error_popup("AndroidAutoStart environment check failed", format_check_result(result))
            return False
        if result.warnings:
            self.log("Environment check passed with warnings")
        return True

    def start_services(self) -> None:
        script = self.root / "scripts" / "start_all.ps1"
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        self.log(f"Starting services via: {' '.join(command)}")
        self.process = subprocess.Popen(
            command,
            cwd=str(self.root),
            env=build_runtime_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.started_at = time.monotonic()
        threading.Thread(target=self._pipe_output, daemon=True).start()

    def _pipe_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.log(f"[start_all] {line.rstrip()}")

    def finish_services(self) -> None:
        script = self.root / "scripts" / "finish_all.ps1"
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        self.log("Stopping services")
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.stdout:
            self.log(completed.stdout.rstrip())
        if completed.stderr:
            self.log(completed.stderr.rstrip())

    def restart_services(self) -> None:
        self.restart_count += 1
        self.log(f"Restarting services, attempt {self.restart_count}/{MAX_RESTARTS}")
        self.finish_services()
        time.sleep(2)
        self.start_services()

    def poll_status(self) -> dict[str, object]:
        status = collect_status(self.root)
        status_path = write_status_file(self.root, status)
        self.log(f"Service status written to {status_path}")
        self.log("\n" + format_status(status))
        return status

    def maybe_open_web(self, status: dict[str, object]) -> None:
        if self.web_opened:
            return
        services = status.get("services", {})
        if isinstance(services, dict):
            web = services.get("web", {})
            if isinstance(web, dict) and web.get("status") == "running":
                webbrowser.open("http://127.0.0.1:5173")
                self.web_opened = True
                self.log("Opened web admin: http://127.0.0.1:5173")

    def read_command(self) -> str | None:
        try:
            if not msvcrt.kbhit():
                return None
            return msvcrt.getwch().lower()
        except OSError:
            return None

    def monitor(self) -> int:
        self.log("Commands: s=status, r=restart, q=quit launcher, x=stop services and quit")
        while True:
            command = self.read_command()
            if command == "s":
                self.poll_status()
            elif command == "r":
                self.restart_services()
            elif command == "q":
                self.log("Exiting launcher without stopping services")
                return 0
            elif command == "x":
                self.finish_services()
                return 0

            if self.process and self.process.poll() is not None:
                self.log(f"start_all exited with code {self.process.returncode}")
                if self.restart_count < MAX_RESTARTS:
                    self.restart_services()
                else:
                    show_error_popup("AndroidAutoStart service stopped", "Services stopped repeatedly. Please check launcher logs.")
                    return 1

            status = self.poll_status()
            self.maybe_open_web(status)
            in_grace = (time.monotonic() - self.started_at) < STARTUP_GRACE_SECONDS
            if in_grace and not all_required_running(status):
                self.log("Waiting for services to become ready")
            elif not all_required_running(status) and self.restart_count < MAX_RESTARTS:
                self.restart_services()
            elif not all_required_running(status):
                show_error_popup("AndroidAutoStart service check failed", "One or more services are not running. Please check launcher logs.")
                return 1

            time.sleep(MONITOR_INTERVAL_SECONDS)

    def run(self) -> int:
        self.log(f"Project root: {self.root}")
        self.log(f"Launcher log: {self.log_path}")
        if not self.run_checks():
            return 1
        self.start_services()
        return self.monitor()


def main() -> int:
    parser = argparse.ArgumentParser(description="Android auto Windows start launcher")
    parser.add_argument("--check-only", action="store_true", help="run environment checks and exit")
    parser.add_argument("--status-only", action="store_true", help="print service status and exit")
    parser.add_argument("--no-popup", action="store_true", help="do not show popup dialogs")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    launcher = Launcher(root)
    if args.status_only:
        launcher.poll_status()
        return 0
    if args.check_only:
        if args.no_popup:
            result = run_environment_check(root)
            print(format_check_result(result))
            return 0 if result.ok else 1
        return 0 if launcher.run_checks() else 1
    return launcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
