from pathlib import Path

from app.logger import configure_device_file_logger, ensure_runtime_dirs, sanitize_filename


def test_ensure_runtime_dirs(tmp_path: Path) -> None:
    logs_dir, screenshots_dir = ensure_runtime_dirs(tmp_path)

    assert logs_dir == tmp_path / "logs"
    assert screenshots_dir == tmp_path / "screenshots"
    assert logs_dir.is_dir()
    assert screenshots_dir.is_dir()


def test_configure_device_file_logger_uses_device_name(tmp_path: Path) -> None:
    log_path = configure_device_file_logger(device_name="device_01", runtime_dir=tmp_path)

    assert log_path == tmp_path / "logs" / "device_01.log"
    assert log_path.parent.is_dir()


def test_sanitize_filename() -> None:
    assert sanitize_filename("FMR0223830012928") == "FMR0223830012928"
    assert sanitize_filename("设备 01/测试") == "01"
