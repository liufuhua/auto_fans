import json
import re
import shlex
import subprocess
from datetime import timedelta

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now_beijing
from app.core.exceptions import AppException
from app.models.device import Device
from app.schemas.common import PageParams, PageResult
from app.schemas.device import DeviceItem, DevicePayload

DEFAULT_PUBLIC_IP_URL = "https://ipinfo.io/json"
DEFAULT_IP138_LOOKUP_URL_TEMPLATE = "https://www.ip138.com/iplookup.php?ip={ip}&action=2"
DEFAULT_USER_AGENT = "Mozilla/5.0"
HEARTBEAT_OFFLINE_SECONDS = 90


def appium_server_url_from_port(appium_port: int | None) -> str | None:
    if appium_port is None:
        return None
    return f"http://127.0.0.1:{appium_port}"


def to_device_item(device: Device) -> DeviceItem:
    return DeviceItem.model_validate(device)


def get_device_or_404(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise AppException("设备不存在", code="DEVICE_NOT_FOUND", status_code=404)
    return device


def _apply_device_filters(
    statement: Select[tuple[Device]],
    keyword: str | None,
    enabled_status: str | None,
    runtime_status: str | None,
) -> Select[tuple[Device]]:
    if keyword:
        keyword_like = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                Device.name.like(keyword_like),
                Device.udid.like(keyword_like),
                Device.remark.like(keyword_like),
            )
        )
    if enabled_status:
        statement = statement.where(Device.enabled_status == enabled_status)
    if runtime_status:
        statement = statement.where(Device.runtime_status == runtime_status)
    return statement


def list_devices(
    db: Session,
    page_params: PageParams,
    keyword: str | None,
    enabled_status: str | None,
    runtime_status: str | None,
) -> PageResult[DeviceItem]:
    mark_stale_devices_offline(db)
    statement = _apply_device_filters(select(Device), keyword, enabled_status, runtime_status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    devices = db.scalars(
        statement.order_by(Device.id.asc())
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()
    return PageResult(items=[to_device_item(device) for device in devices], total=total)


def list_device_options(db: Session) -> list[DeviceItem]:
    mark_stale_devices_offline(db)
    devices = db.scalars(select(Device).order_by(Device.id.asc())).all()
    return [to_device_item(device) for device in devices]


def mark_stale_devices_offline(db: Session) -> None:
    threshold = now_beijing() - timedelta(seconds=HEARTBEAT_OFFLINE_SECONDS)
    stale_devices = db.scalars(
        select(Device)
        .where(Device.runtime_status != "offline")
        .where(Device.last_heartbeat_at.is_not(None))
        .where(Device.last_heartbeat_at < threshold)
    ).all()
    if not stale_devices:
        return
    for device in stale_devices:
        device.runtime_status = "offline"
    db.add_all(stale_devices)
    db.commit()


def ensure_device_unique(
    db: Session,
    *,
    name: str,
    udid: str,
    system_port: int,
    exclude_device_id: int | None = None,
) -> None:
    statement = select(Device).where(
        or_(Device.name == name, Device.udid == udid, Device.system_port == system_port)
    )
    if exclude_device_id is not None:
        statement = statement.where(Device.id != exclude_device_id)
    existing = db.scalar(statement)
    if existing is None:
        return
    if existing.name == name:
        raise AppException("设备名称已存在", code="DEVICE_NAME_EXISTS", status_code=409)
    if existing.udid == udid:
        raise AppException("ADB UDID 已存在", code="DEVICE_UDID_EXISTS", status_code=409)
    raise AppException("systemPort 已存在", code="DEVICE_SYSTEM_PORT_EXISTS", status_code=409)


def create_device(db: Session, payload: DevicePayload) -> DeviceItem:
    name = payload.name.strip()
    udid = payload.udid.strip()
    ensure_device_unique(db, name=name, udid=udid, system_port=payload.system_port)
    device = Device(
        name=name,
        udid=udid,
        device_model=payload.device_model,
        system_port=payload.system_port,
        enabled_status="enabled",
        runtime_status="offline",
        province=payload.province,
        appium_server_url=appium_server_url_from_port(payload.appium_port),
        remark=payload.remark,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return to_device_item(device)


def update_device(db: Session, device_id: int, payload: DevicePayload) -> DeviceItem:
    device = get_device_or_404(db, device_id)
    name = payload.name.strip()
    udid = payload.udid.strip()
    ensure_device_unique(
        db,
        name=name,
        udid=udid,
        system_port=payload.system_port,
        exclude_device_id=device_id,
    )
    device.name = name
    device.udid = udid
    device.device_model = payload.device_model
    device.system_port = payload.system_port
    device.province = payload.province
    device.appium_server_url = appium_server_url_from_port(payload.appium_port)
    device.remark = payload.remark
    db.add(device)
    db.commit()
    db.refresh(device)
    return to_device_item(device)


def set_device_enabled_status(db: Session, device_id: int, enabled_status: str) -> DeviceItem:
    device = get_device_or_404(db, device_id)
    device.enabled_status = enabled_status
    if enabled_status == "disabled":
        device.runtime_status = "offline"
    db.add(device)
    db.commit()
    db.refresh(device)
    return to_device_item(device)


def refresh_device_public_ip(db: Session, device_id: int) -> DeviceItem:
    device = get_device_or_404(db, device_id)
    ip = _fetch_device_public_ip(device.udid)
    html = _fetch_device_url(
        device.udid,
        DEFAULT_IP138_LOOKUP_URL_TEMPLATE.format(ip=ip),
    )
    location, province, city = _parse_ip138_location(html)

    device.public_ip = ip
    device.province = province
    device.ip_province = province
    device.ip_city = city
    device.ip_region = location
    device.ip_checked_at = now_beijing()
    db.add(device)
    db.commit()
    db.refresh(device)
    return to_device_item(device)


def _run_adb(args: list[str], *, timeout_seconds: int = 20, check: bool = True) -> str:
    try:
        completed = subprocess.run(
            ["adb", *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise AppException("ADB 不存在，请检查 Android SDK 配置", code="ADB_NOT_FOUND") from exc
    except subprocess.TimeoutExpired as exc:
        raise AppException("ADB 命令超时", code="ADB_TIMEOUT") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise AppException(message or "ADB 命令执行失败", code="ADB_COMMAND_FAILED") from exc

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if check and completed.returncode != 0:
        message = (stderr or stdout or f"adb exited with code {completed.returncode}").strip()
        raise AppException(message or "ADB 命令执行失败", code="ADB_COMMAND_FAILED")
    return stdout.strip()


def _run_device_shell(udid: str, command: str, *, timeout_seconds: int = 25) -> str:
    return _run_adb(["-s", udid, "shell", command], timeout_seconds=timeout_seconds)


def _fetch_device_url(udid: str, url: str, *, timeout_seconds: int = 20) -> str:
    curl_path = _run_adb(
        ["-s", udid, "shell", "command", "-v", "curl"],
        timeout_seconds=5,
        check=False,
    )
    wget_path = ""
    if not curl_path:
        wget_path = _run_adb(
            ["-s", udid, "shell", "command", "-v", "wget"],
            timeout_seconds=5,
            check=False,
        )

    if curl_path:
        return _run_device_shell(
            udid,
            "curl -L --connect-timeout 8 "
            f"--max-time {timeout_seconds} "
            f"-A {shlex.quote(DEFAULT_USER_AGENT)} -s {shlex.quote(url)}",
            timeout_seconds=timeout_seconds + 5,
        )
    if wget_path:
        return _run_device_shell(
            udid,
            f"wget -T {timeout_seconds} --user-agent={shlex.quote(DEFAULT_USER_AGENT)} "
            f"-qO- {shlex.quote(url)}",
            timeout_seconds=timeout_seconds + 5,
        )
    raise AppException(
        "手机 shell 里没有 curl/wget，无法从手机侧查询公网 IP",
        code="DEVICE_HTTP_CLIENT_NOT_FOUND",
        status_code=400,
    )


def _fetch_device_public_ip(udid: str) -> str:
    raw = _fetch_device_url(udid, DEFAULT_PUBLIC_IP_URL)
    if not raw:
        raise AppException("手机侧公网 IP 查询返回为空", code="DEVICE_IP_EMPTY")
    try:
        data = json.loads(raw)
        ip = str(data.get("ip") or data.get("query") or "").strip()
    except json.JSONDecodeError:
        ip = raw.strip()
    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
        raise AppException(f"无法解析手机公网 IP：{raw[:100]}", code="DEVICE_IP_PARSE_FAILED")
    return ip


def _parse_ip138_location(html: str) -> tuple[str, str, str]:
    location = ""
    asn_match = re.search(
        r"<td[^>]*>\s*ASN归属地\s*</td>\s*<td[^>]*>\s*<span[^>]*>(.*?)</span>",
        html,
        flags=re.S,
    )
    if asn_match:
        location = _strip_html(asn_match.group(1))

    if not location:
        row_match = re.search(
            r"<td>\d{1,3}(?:\.\d{1,3}){3}</td>\s*"
            r"<td>\d{1,3}(?:\.\d{1,3}){3}</td>\s*"
            r"<td>(.*?)</td>\s*<td>(.*?)</td>",
            html,
            flags=re.S,
        )
        if row_match:
            location = _strip_html(row_match.group(1))

    if not location:
        raise AppException("ip138 页面里没有解析到归属地", code="IP138_LOCATION_PARSE_FAILED")

    province = _extract_china_province(location)
    city = _extract_china_city(location, province)
    return location, province, city


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", value)).strip()


def _extract_china_province(location: str) -> str:
    text = location.removeprefix("中国")
    for city in ("北京市", "上海市", "天津市", "重庆市"):
        if text.startswith(city):
            return city.removesuffix("市")
    for suffix in ("省", "自治区", "特别行政区"):
        index = text.find(suffix)
        if index > 0:
            return text[: index + len(suffix)]
    return text[:2] if text else ""


def _extract_china_city(location: str, province: str) -> str:
    text = location.removeprefix("中国")
    if province in {"北京", "上海", "天津", "重庆"}:
        return f"{province}市"
    text = text.removeprefix(province)
    match = re.match(r"(.+?市)", text)
    return match.group(1) if match else ""
