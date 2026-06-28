from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from env_check import build_runtime_env, show_error_popup
from service_status import collect_status, format_status, write_status_file


class FinishLauncher:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_dir = root / "logs" / "launcher"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"finish_{stamp}.log"

    def log(self, message: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        try:
            print(line)
        except OSError:
            pass

    def run(self) -> int:
        script = self.root / "scripts" / "finish_all.ps1"
        if not script.exists():
            message = f"Missing finish script: {script}"
            self.log(message)
            show_error_popup("AndroidAutoFinish failed", message)
            return 1

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        self.log(f"Stopping services via: {' '.join(command)}")
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            env=build_runtime_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.stdout:
            self.log(completed.stdout.rstrip())
        if completed.stderr:
            self.log(completed.stderr.rstrip())

        status = collect_status(self.root)
        status_path = write_status_file(self.root, status)
        self.log(f"Service status written to {status_path}")
        self.log("\n" + format_status(status))

        return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Android auto Windows finish launcher")
    parser.add_argument("--status-only", action="store_true", help="print service status and exit")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    launcher = FinishLauncher(root)
    if args.status_only:
        status = collect_status(root)
        write_status_file(root, status)
        print(format_status(status))
        return 0
    return launcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
