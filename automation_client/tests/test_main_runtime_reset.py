import logging

from app.api_client import AutomationApiError, AutomationRuntimeState
from app.main import reset_runtime_on_client_shutdown, reset_runtime_on_client_start


class FakeApiClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.auto_stop_requests = []

    def auto_stop_automation_runtime(self, **kwargs):
        self.auto_stop_requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return AutomationRuntimeState(
            business_status="stopped",
            remark=str(kwargs["remark"]),
        )


def test_reset_runtime_on_client_start_forces_manual_start() -> None:
    api_client = FakeApiClient()

    reset_runtime_on_client_start(api_client)  # type: ignore[arg-type]

    assert api_client.auto_stop_requests == [
        {
            "remark": "automation client startup: require manual start",
            "force": True,
        }
    ]


def test_reset_runtime_on_client_start_logs_api_error(caplog) -> None:
    api_client = FakeApiClient(error=AutomationApiError("connection failed"))

    with caplog.at_level(logging.WARNING):
        reset_runtime_on_client_start(api_client)  # type: ignore[arg-type]

    assert api_client.auto_stop_requests == [
        {
            "remark": "automation client startup: require manual start",
            "force": True,
        }
    ]
    assert "failed to reset automation runtime on client startup" in caplog.text


def test_reset_runtime_on_client_shutdown_forces_manual_start() -> None:
    api_client = FakeApiClient()

    reset_runtime_on_client_shutdown(api_client)  # type: ignore[arg-type]

    assert api_client.auto_stop_requests == [
        {
            "remark": "automation client shutdown: require manual start",
            "force": True,
        }
    ]


def test_reset_runtime_on_client_shutdown_logs_api_error(caplog) -> None:
    api_client = FakeApiClient(error=AutomationApiError("connection failed"))

    with caplog.at_level(logging.WARNING):
        reset_runtime_on_client_shutdown(api_client)  # type: ignore[arg-type]

    assert api_client.auto_stop_requests == [
        {
            "remark": "automation client shutdown: require manual start",
            "force": True,
        }
    ]
    assert "failed to reset automation runtime on client shutdown" in caplog.text
