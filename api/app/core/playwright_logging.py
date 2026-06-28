from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


PLAYWRIGHT_LOGGER_NAMES = (
    "app.services.comment_recheck_worker",
    "app.services.douyin_comment_checker",
    "app.services.douyin_playwright_session",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _new_log_path() -> Path:
    log_dir = _project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"playwright-{timestamp}.txt"


@contextmanager
def playwright_log_file() -> Iterator[Path]:
    log_path = _new_log_path()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )

    loggers = [logging.getLogger(name) for name in PLAYWRIGHT_LOGGER_NAMES]
    for logger in loggers:
        logger.addHandler(handler)

    try:
        yield log_path
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()
