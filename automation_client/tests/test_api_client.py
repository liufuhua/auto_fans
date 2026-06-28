import json
from datetime import datetime

import httpx

from app.api_client import AutomationApiClient


def test_heartbeat_device_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/devices/heartbeat"
        assert request.read() == (
            b'{"udid":"device-1","deviceName":"device_01","systemPort":8201,'
            b'"runtimeStatus":"idle","remark":"test"}'
        )
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "deviceId": 1,
                    "udid": "device-1",
                    "runtimeStatus": "idle",
                    "lastHeartbeatAt": "2026-05-07T09:30:00",
                },
            },
        )

    transport = httpx.MockTransport(handler)
    client = AutomationApiClient("http://testserver/api", transport=transport)
    result = client.heartbeat_device(
        udid="device-1",
        device_name="device_01",
        system_port=8201,
        runtime_status="idle",
        remark="test",
    )

    assert len(requests) == 1
    assert result.device_id == 1
    assert result.udid == "device-1"
    assert result.runtime_status == "idle"
    assert result.last_heartbeat_at == datetime(2026, 5, 7, 9, 30)


def test_get_automation_runtime_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/runtime"
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "businessStatus": "running",
                    "startedAt": "2026-05-11T09:30:00",
                    "stoppedAt": None,
                    "updatedAt": "2026-05-11T09:31:00",
                    "remark": "admin start",
                },
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.get_automation_runtime()

    assert len(requests) == 1
    assert result.business_status == "running"
    assert result.started_at == datetime(2026, 5, 11, 9, 30)
    assert result.stopped_at is None
    assert result.updated_at == datetime(2026, 5, 11, 9, 31)
    assert result.remark == "admin start"


def test_list_device_configs_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/devices/configs"
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": [
                    {
                        "id": 6,
                        "name": "device_02",
                        "udid": "10AG3R2JNF001KK",
                        "systemPort": 8202,
                        "enabledStatus": "enabled",
                        "appiumServerUrl": "http://127.0.0.1:4727",
                    }
                ],
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.list_device_configs()

    assert len(requests) == 1
    assert result[0].id == 6
    assert result[0].name == "device_02"
    assert result[0].udid == "10AG3R2JNF001KK"
    assert result[0].system_port == 8202
    assert result[0].enabled_status == "enabled"
    assert result[0].appium_server_url == "http://127.0.0.1:4727"


def test_auto_stop_automation_runtime_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/runtime/auto-stop"
        assert json.loads(request.read()) == {"remark": "no task available", "force": False}
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "businessStatus": "stopped",
                    "startedAt": "2026-05-11T09:30:00",
                    "stoppedAt": "2026-05-11T09:35:00",
                    "updatedAt": "2026-05-11T09:35:00",
                    "remark": "no task available",
                },
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.auto_stop_automation_runtime(remark="no task available")

    assert len(requests) == 1
    assert result.business_status == "stopped"
    assert result.stopped_at == datetime(2026, 5, 11, 9, 35)
    assert result.remark == "no task available"


def test_claim_task_request_and_task_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/tasks/claim"
        assert json.loads(request.read()) == {
            "udid": "device-1",
            "publishAccount": "测试账号01",
        }
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "hasTask": True,
                    "taskId": 1,
                    "taskItemId": 2,
                    "doctorId": 3,
                    "doctorName": "张明山",
                    "doctorRealName": "张明山教授",
                    "keywordId": 4,
                    "keyword": "脑膜瘤",
                    "searchWord": "脑膜瘤",
                    "commentBankItemId": 5,
                    "commentContent": "测试评论内容",
                },
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.claim_task(udid="device-1", publish_account="测试账号01")

    assert len(requests) == 1
    assert result.has_task is True
    assert result.task_id == 1
    assert result.task_item_id == 2
    assert result.doctor_id == 3
    assert result.doctor_name == "张明山"
    assert result.doctor_real_name == "张明山教授"
    assert result.keyword_id == 4
    assert result.keyword == "脑膜瘤"
    assert result.search_word == "脑膜瘤"
    assert result.comment_bank_item_id == 5
    assert result.comment_content == "测试评论内容"


def test_claim_task_request_and_empty_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {"hasTask": False},
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.claim_task(udid="device-1", publish_account="测试账号01")

    assert result.has_task is False
    assert result.task_id is None
    assert result.comment_content is None


def test_claim_task_empty_response_keeps_reason() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {"hasTask": False, "reason": "device_pool_empty"},
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.claim_task(udid="device-1", publish_account="test-account")

    assert result.has_task is False
    assert result.reason == "device_pool_empty"


def test_start_task_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/tasks/2/start"
        assert json.loads(request.read()) == {
            "udid": "device-1",
            "commentBankItemId": 5,
            "publishAccount": "测试账号01",
        }
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "resultId": 8,
                    "status": "running",
                },
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.start_task(
        task_item_id=2,
        udid="device-1",
        comment_bank_item_id=5,
        publish_account="测试账号01",
    )

    assert len(requests) == 1
    assert result.result_id == 8
    assert result.status == "running"


def test_report_task_request_and_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/automation/tasks/2/report"
        assert json.loads(request.read()) == {
            "udid": "device-1",
            "resultId": 8,
            "commentBankItemId": 5,
            "publishAccount": "测试账号01",
            "status": "success",
            "videoLink": "https://v.douyin.com/test/",
            "resultSummary": None,
            "failReason": None,
            "screenshotUrl": None,
            "logUrl": None,
        }
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "resultId": 8,
                    "status": "success",
                },
            },
        )

    client = AutomationApiClient("http://testserver/api", transport=httpx.MockTransport(handler))
    result = client.report_task(
        task_item_id=2,
        udid="device-1",
        result_id=8,
        comment_bank_item_id=5,
        publish_account="测试账号01",
        status="success",
        video_link="https://v.douyin.com/test/",
    )

    assert len(requests) == 1
    assert result.result_id == 8
    assert result.status == "success"
