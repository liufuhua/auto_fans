from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime

from app.config import settings

DEFAULT_PUBLIC_IP_URL = "https://ipinfo.io/json"
DEFAULT_IP138_LOOKUP_URL_TEMPLATE = "https://www.ip138.com/iplookup.php?ip={ip}&action=2"
DEFAULT_USER_AGENT = "Mozilla/5.0"


class DeviceRegionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceNetworkRegion:
    udid: str
    ip: str
    country: str
    province: str
    city: str
    isp: str
    source: str
    queried_at: str


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Android device public network region.")
    parser.add_argument("--udid", required=True)
    parser.add_argument("--adb-path", default=settings.adb_path)
    parser.add_argument("--public-ip-url", default=DEFAULT_PUBLIC_IP_URL)
    parser.add_argument("--ip138-url-template", default=DEFAULT_IP138_LOOKUP_URL_TEMPLATE)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser.parse_args()


def run_adb_shell(
    *,
    adb_path: str,
    udid: str,
    shell_command: str,
    timeout_seconds: int,
) -> str:
    try:
        completed = subprocess.run(
            [adb_path, "-s", udid, "shell", shell_command],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise DeviceRegionError(f"ADB 不存在：{adb_path}") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise DeviceRegionError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise DeviceRegionError("手机网络地区查询超时") from exc
    return completed.stdout.strip()


def fetch_device_url(
    *,
    adb_path: str,
    udid: str,
    url: str,
    user_agent: str,
    timeout_seconds: int,
) -> str:
    curl_path = run_adb(
        adb_path=adb_path,
        udid=udid,
        args=["shell", "command", "-v", "curl"],
        timeout_seconds=5,
        check=False,
    )
    wget_path = ""
    if not curl_path:
        wget_path = run_adb(
            adb_path=adb_path,
            udid=udid,
            args=["shell", "command", "-v", "wget"],
            timeout_seconds=5,
            check=False,
        )

    if curl_path:
        return run_adb_shell(
            adb_path=adb_path,
            udid=udid,
            shell_command=(
                "curl -L --connect-timeout 8 "
                f"--max-time {timeout_seconds} "
                f"-A {shlex.quote(user_agent)} -s {shlex.quote(url)}"
            ),
            timeout_seconds=timeout_seconds + 5,
        )
    if wget_path:
        return run_adb_shell(
            adb_path=adb_path,
            udid=udid,
            shell_command=(
                f"wget -T {timeout_seconds} "
                f"--user-agent={shlex.quote(user_agent)} -qO- {shlex.quote(url)}"
            ),
            timeout_seconds=timeout_seconds + 5,
        )
    raise DeviceRegionError(
        "手机 shell 里没有 curl/wget，无法直接从手机侧查询公网 IP。"
        "可以安装支持 curl 的调试环境，或改为让手机浏览器访问自建检测接口。"
    )


def fetch_device_public_ip(
    *,
    adb_path: str,
    udid: str,
    public_ip_url: str,
    user_agent: str,
    timeout_seconds: int,
) -> str:
    raw = fetch_device_url(
        adb_path=adb_path,
        udid=udid,
        url=public_ip_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    if not raw:
        raise DeviceRegionError("手机侧公网 IP 查询返回为空")

    try:
        data = json.loads(raw)
        ip = str(data.get("ip") or data.get("query") or "").strip()
    except json.JSONDecodeError:
        ip = raw.strip()

    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
        raise DeviceRegionError(f"无法解析手机公网 IP：{raw[:200]}")
    return ip


def parse_ip138_location(html: str) -> tuple[str, str, str]:
    location = ""
    asn_match = re.search(
        r"<td[^>]*>\s*ASN归属地\s*</td>\s*<td[^>]*>\s*<span[^>]*>(.*?)</span>",
        html,
        flags=re.S,
    )
    if asn_match:
        location = strip_html(asn_match.group(1))

    if not location:
        row_match = re.search(
            r"<td>\d{1,3}(?:\.\d{1,3}){3}</td>\s*"
            r"<td>\d{1,3}(?:\.\d{1,3}){3}</td>\s*"
            r"<td>(.*?)</td>\s*<td>(.*?)</td>",
            html,
            flags=re.S,
        )
        if row_match:
            location = strip_html(row_match.group(1))

    if not location:
        raise DeviceRegionError("ip138 页面里没有解析到归属地")

    province = extract_china_province(location)
    city = extract_china_city(location, province)
    return location, province, city


def strip_html(value: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", value)).strip()


def extract_china_province(location: str) -> str:
    text = location.removeprefix("中国")
    direct_cities = ("北京市", "上海市", "天津市", "重庆市")
    for city in direct_cities:
        if text.startswith(city):
            return city.removesuffix("市")

    for suffix in ("省", "自治区", "特别行政区"):
        index = text.find(suffix)
        if index > 0:
            return text[: index + len(suffix)]
    return text[:2] if text else ""


def extract_china_city(location: str, province: str) -> str:
    text = location.removeprefix("中国")
    if province in {"北京", "上海", "天津", "重庆"}:
        return f"{province}市"
    text = text.removeprefix(province)
    match = re.match(r"(.+?市)", text)
    return match.group(1) if match else ""


def run_adb(
    *,
    adb_path: str,
    udid: str,
    args: list[str],
    timeout_seconds: int,
    check: bool = True,
) -> str:
    try:
        completed = subprocess.run(
            [adb_path, "-s", udid, *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise DeviceRegionError(f"ADB 不存在：{adb_path}") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise DeviceRegionError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise DeviceRegionError("ADB 命令超时") from exc
    return completed.stdout.strip()


def query_device_network_province(
    *,
    udid: str,
    adb_path: str = "adb",
    public_ip_url: str = DEFAULT_PUBLIC_IP_URL,
    ip138_url_template: str = DEFAULT_IP138_LOOKUP_URL_TEMPLATE,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: int = 20,
) -> DeviceNetworkRegion:
    """让手机设备自己发起公网 IP 查询，并返回网络出口所属省份。

    这里不能用电脑上的 Python httpx 请求，因为那查到的是电脑网络出口。
    必须通过 `adb shell` 在手机侧执行 curl/wget，才能拿到手机当前网络
    对应的公网 IP 和省份。
    """

    ip = fetch_device_public_ip(
        adb_path=adb_path,
        udid=udid,
        public_ip_url=public_ip_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    lookup_url = ip138_url_template.format(ip=ip)
    html = fetch_device_url(
        adb_path=adb_path,
        udid=udid,
        url=lookup_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    if not html:
        raise DeviceRegionError("手机侧 ip138 查询返回为空")
    location, province, city = parse_ip138_location(html)

    return DeviceNetworkRegion(
        udid=udid,
        ip=ip,
        country="中国" if location.startswith("中国") else "",
        province=province,
        city=city,
        isp=location,
        source="ip138",
        queried_at=datetime.now().isoformat(timespec="seconds"),
    )


def main() -> None:
    args = parse_args()
    log_step("开始查询手机网络所属省份")
    log_step(f"设备：{args.udid}")
    region = query_device_network_province(
        udid=args.udid,
        adb_path=args.adb_path,
        public_ip_url=args.public_ip_url,
        ip138_url_template=args.ip138_url_template,
        user_agent=args.user_agent,
        timeout_seconds=args.timeout_seconds,
    )
    log_step("查询成功")
    print(f"设备：{region.udid}")
    print(f"公网 IP：{region.ip}")
    print(f"国家：{region.country}")
    print(f"省份：{region.province}")
    print(f"城市：{region.city}")
    print(f"归属地：{region.isp}")
    print(f"来源：{region.source}")
    print(f"查询时间：{region.queried_at}")


if __name__ == "__main__":
    main()
