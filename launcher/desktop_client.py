from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import webview

from env_check import build_runtime_env, format_check_result, run_environment_check, show_error_popup
from service_status import all_required_running, collect_status, format_status, write_status_file


WEB_URL = "http://127.0.0.1:5173"
STARTUP_TIMEOUT_SECONDS = 90
STATUS_INTERVAL_SECONDS = 2


class DesktopClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_dir = root / "logs" / "launcher"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"desktop_{stamp}.log"
        self.process: subprocess.Popen[str] | None = None
        self.window: webview.Window | None = None
        self.stop_requested = False
        self.finish_requested = False

    def log(self, message: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def html(self, title: str, body: str) -> str:
        return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <style>
    body {{
      margin: 0;
      display: grid;
      min-height: 100vh;
      place-items: center;
      background: #f5f7fb;
      color: #111827;
      font-family: "Microsoft YaHei", Arial, sans-serif;
    }}
    main {{
      width: min(620px, calc(100vw - 48px));
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      background: #fff;
      padding: 28px;
      box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    pre {{
      overflow: auto;
      margin: 14px 0 0;
      border-radius: 6px;
      background: #f3f4f6;
      padding: 12px;
      color: #374151;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <div>{body}</div>
  </main>
</body>
</html>
"""

    def set_html(self, title: str, body: str) -> None:
        if self.window:
            self.window.load_html(self.html(title, body))

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
        self.log(f"Starting services: {' '.join(command)}")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
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
            creationflags=creationflags,
        )
        threading.Thread(target=self.pipe_process_output, daemon=True).start()

    def pipe_process_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.log(f"[start_all] {line.rstrip()}")

    def finish_services(self) -> None:
        if self.finish_requested:
            return
        self.finish_requested = True

        script = self.root / "scripts" / "finish_all.ps1"
        if not script.exists():
            self.log(f"Missing finish script: {script}")
            return
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        self.log("Stopping all services")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        completed = subprocess.run(
            command,
            cwd=str(self.root),
            env=build_runtime_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=60,
        )
        if completed.stdout:
            self.log(completed.stdout.rstrip())
        if completed.stderr:
            self.log(completed.stderr.rstrip())

    def wait_until_ready(self) -> bool:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline and not self.stop_requested:
            if self.process and self.process.poll() is not None:
                self.log(f"start_all exited: code={self.process.returncode}")
                return False

            status = collect_status(self.root)
            write_status_file(self.root, status)
            self.log("\n" + format_status(status))
            if all_required_running(status):
                return True

            time.sleep(STATUS_INTERVAL_SECONDS)
        return False

    def run_startup(self) -> None:
        self.log(f"Project root: {self.root}")
        self.log(f"Desktop client log: {self.log_path}")
        result = run_environment_check(self.root)
        self.log(format_check_result(result))
        if not result.ok:
            message = format_check_result(result)
            self.set_html("环境检查失败", f"<pre>{message}</pre>")
            show_error_popup("AutoFans 环境检查失败", message)
            return

        self.set_html("正在启动服务", "请稍等，客户端正在启动 API、Web、Appium 和业务客户端。")
        self.start_services()
        if self.wait_until_ready():
            self.log(f"Loading web admin: {WEB_URL}")
            if self.window:
                self.window.load_url(WEB_URL)
            return

        self.set_html("服务启动失败", f"请查看日志：<pre>{self.log_path}</pre>")
        show_error_popup("AutoFans 服务启动失败", f"服务未能全部启动，请查看日志：\n{self.log_path}")

    def on_closed(self) -> None:
        self.stop_requested = True


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> None:
    client = DesktopClient(project_root())
    client.window = webview.create_window(
        "Android Auto Test",
        html=client.html("正在准备客户端", "正在检查环境并启动本地服务。"),
        width=1280,
        height=820,
        min_size=(1024, 680),
    )
    client.window.events.closed += client.on_closed
    try:
        webview.start(client.run_startup, private_mode=False)
    finally:
        client.stop_requested = True
        client.finish_services()


if __name__ == "__main__":
    main()
