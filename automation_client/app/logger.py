from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from logging.handlers import RotatingFileHandler
import re
import sys
from pathlib import Path
from typing import Iterator

LOG_FORMAT = (
    "%(asctime)s %(levelname)s [%(name)s] "
    "%(device_context)s%(message)s"
)
DEVICE_LOG_MAX_BYTES = 5 * 1024 * 1024
DEVICE_LOG_BACKUP_COUNT = 3

logging.raiseExceptions = False

_LOG_CONTEXT: ContextVar[dict[str, str]] = ContextVar("log_context", default={})
_OLD_RECORD_FACTORY = logging.getLogRecordFactory()
_RECORD_FACTORY_INSTALLED = False


def _current_context() -> dict[str, str]:
    return dict(_LOG_CONTEXT.get())


def _format_device_context(context: dict[str, str]) -> str:
    parts = []
    for key in ("device_name", "udid", "task_item_id", "result_id"):
        value = context.get(key)
        if value:
            parts.append(f"{key}={value}")
    return f"[{' '.join(parts)}] " if parts else ""


def _install_record_factory() -> None:
    global _RECORD_FACTORY_INSTALLED
    if _RECORD_FACTORY_INSTALLED:
        return

    def record_factory(*args, **kwargs):
        record = _OLD_RECORD_FACTORY(*args, **kwargs)
        context = _current_context()
        record.device_name = context.get("device_name", "")
        record.udid = context.get("udid", "")
        record.task_item_id = context.get("task_item_id", "")
        record.result_id = context.get("result_id", "")
        record.device_log_path = context.get("log_file_path", "")
        record.device_context = _format_device_context(context)
        return record

    logging.setLogRecordFactory(record_factory)
    _RECORD_FACTORY_INSTALLED = True


def configure_stdio_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


class DeviceLogFilter(logging.Filter):
    def __init__(self, *, device_name: str, log_path: Path) -> None:
        super().__init__()
        self.device_name = device_name
        self.log_path = str(log_path)

    def filter(self, record: logging.LogRecord) -> bool:
        return (
            getattr(record, "device_name", "") == self.device_name
            and getattr(record, "device_log_path", "") == self.log_path
        )


def configure_logging(debug: bool = False) -> None:
    _install_record_factory()
    configure_stdio_encoding()
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
    )


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def ensure_runtime_dirs(runtime_dir: str | Path = "runtime") -> tuple[Path, Path]:
    root = Path(runtime_dir)
    logs_dir = root / "logs"
    screenshots_dir = root / "screenshots"
    logs_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir, screenshots_dir


def configure_device_file_logger(
    *,
    device_name: str,
    runtime_dir: str | Path = "runtime",
    debug: bool = False,
) -> Path:
    _install_record_factory()
    logs_dir, _screenshots_dir = ensure_runtime_dirs(runtime_dir)
    log_path = logs_dir / f"{sanitize_filename(device_name)}.log"
    handler_name = f"device-file:{log_path}"

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if getattr(handler, "name", None) == handler_name:
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=DEVICE_LOG_MAX_BYTES,
        backupCount=DEVICE_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.name = handler_name
    handler.setLevel(logging.DEBUG if debug else logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(DeviceLogFilter(device_name=device_name, log_path=log_path))
    root_logger.addHandler(handler)
    root_logger.setLevel(min(root_logger.level or logging.INFO, handler.level))
    return log_path


@contextmanager
def log_context(**values: object) -> Iterator[None]:
    current = _current_context()
    updates = {key: str(value) for key, value in values.items() if value is not None}
    token = _LOG_CONTEXT.set({**current, **updates})
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def format_log_step(message: str) -> str:
    return f"{_format_device_context(_current_context())}{message}"


def append_current_device_log(line: str) -> None:
    log_file_path = _current_context().get("log_file_path")
    if not log_file_path:
        return
    try:
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(log_file_path).open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError:
        return
