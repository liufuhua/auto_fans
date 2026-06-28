from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceEnabledStatus = Literal["enabled", "disabled"]
DeviceRuntimeStatus = Literal["offline", "idle", "running", "exception"]
DeviceModel = Literal["vivo_y52", "huawei_nova_se6"]


class DeviceItem(BaseModel):
    id: int
    name: str
    udid: str
    device_model: DeviceModel = Field(default="huawei_nova_se6", serialization_alias="deviceModel")
    system_port: int = Field(serialization_alias="systemPort")
    enabled_status: DeviceEnabledStatus = Field(serialization_alias="enabledStatus")
    runtime_status: DeviceRuntimeStatus = Field(serialization_alias="runtimeStatus")
    last_heartbeat_at: datetime | None = Field(default=None, serialization_alias="lastHeartbeatAt")
    public_ip: str | None = Field(default=None, serialization_alias="publicIp")
    province: str = ""
    ip_province: str | None = Field(default=None, serialization_alias="ipProvince")
    ip_city: str | None = Field(default=None, serialization_alias="ipCity")
    ip_region: str | None = Field(default=None, serialization_alias="ipRegion")
    ip_checked_at: datetime | None = Field(default=None, serialization_alias="ipCheckedAt")
    appium_server_url: str | None = Field(default=None, serialization_alias="appiumServerUrl")
    remark: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, str_strip_whitespace=True)


class DevicePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    udid: str = Field(min_length=1, max_length=128)
    device_model: DeviceModel = Field(default="huawei_nova_se6", validation_alias="deviceModel")
    system_port: int = Field(validation_alias="systemPort", ge=8200, le=8999)
    appium_port: int | None = Field(default=None, validation_alias="appiumPort", ge=1, le=65535)
    province: str = Field(default="", max_length=32)
    remark: str = Field(default="", max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)
