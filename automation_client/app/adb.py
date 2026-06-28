from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AdbDevice:
    udid: str
    status: str
    raw: str

    @property
    def online(self) -> bool:
        return self.status == "device"


class AdbError(RuntimeError):
    pass


class AdbClient:
    """ADB helper for device discovery."""

    def __init__(self, adb_path: str = "adb") -> None:
        self.adb_path = adb_path

    def devices(self) -> list[AdbDevice]:
        output = self._run(["devices"])
        return parse_adb_devices(output)

    def online_devices(self) -> list[AdbDevice]:
        return [device for device in self.devices() if device.online]

    def _run(self, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                [self.adb_path, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError as exc:
            raise AdbError(f"ADB not found: {self.adb_path}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            message = stderr or stdout or str(exc)
            raise AdbError(message) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError("ADB command timed out") from exc

        return completed.stdout


def parse_adb_devices(output: str) -> list[AdbDevice]:
    devices: list[AdbDevice] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        devices.append(AdbDevice(udid=parts[0], status=parts[1], raw=line))
    return devices
