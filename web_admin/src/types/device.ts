export type DeviceEnabledStatus = 'enabled' | 'disabled'
export type DeviceRuntimeStatus = 'offline' | 'idle' | 'running'
export type DeviceModel = 'vivo_y52' | 'huawei_nova_se6'

export type DeviceItem = {
  id: number
  name: string
  udid: string
  deviceModel: DeviceModel
  systemPort: number
  enabledStatus: DeviceEnabledStatus
  runtimeStatus: DeviceRuntimeStatus
  lastHeartbeatAt?: string
  publicIp?: string
  province: string
  ipProvince?: string
  ipCity?: string
  ipRegion?: string
  ipCheckedAt?: string
  appiumServerUrl?: string | null
  remark: string
  createdAt: string
  updatedAt: string
}

export type DeviceQuery = {
  keyword?: string
  enabledStatus?: DeviceEnabledStatus | ''
  runtimeStatus?: DeviceRuntimeStatus | ''
  page: number
  pageSize: number
}

export type DeviceListResponse = {
  items: DeviceItem[]
  total: number
}

export type DevicePayload = {
  name: string
  udid: string
  deviceModel: DeviceModel
  systemPort: number
  appiumPort?: number | null
  province: string
  remark: string
}
