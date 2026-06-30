import type {
  DeviceEnabledStatus,
  DeviceItem,
  DeviceListResponse,
  DevicePayload,
  DeviceQuery,
} from '../types/device'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const DEVICE_KEY = 'auto_fans_mock_devices'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const now = () => new Date().toISOString()

const seedDevices: DeviceItem[] = Array.from({ length: 8 }).map((_, index) => {
  const order = index + 1
  return {
    id: order,
    name: `device_${String(order).padStart(2, '0')}`,
    udid: `emulator-${5554 + index * 2}`,
    deviceModel: 'huawei_nova_se6',
    systemPort: 8200 + order,
    appiumServerUrl: `http://127.0.0.1:${4723 + order}`,
    enabledStatus: 'enabled',
    runtimeStatus: index < 3 ? 'idle' : 'offline',
    lastHeartbeatAt: index < 3 ? now() : undefined,
    publicIp: '',
    province: '',
    ipProvince: '',
    ipCity: '',
    ipRegion: '',
    ipCheckedAt: undefined,
    remark: '预置 Android 设备配置',
    createdAt: '2026-05-06T09:00:00.000Z',
    updatedAt: '2026-05-06T09:00:00.000Z',
  }
})

const readDevices = (): DeviceItem[] => {
  const raw = localStorage.getItem(DEVICE_KEY)
  if (!raw) {
    localStorage.setItem(DEVICE_KEY, JSON.stringify(seedDevices))
    return seedDevices
  }

  try {
    return JSON.parse(raw) as DeviceItem[]
  } catch {
    localStorage.setItem(DEVICE_KEY, JSON.stringify(seedDevices))
    return seedDevices
  }
}

const writeDevices = (items: DeviceItem[]) => {
  localStorage.setItem(DEVICE_KEY, JSON.stringify(items))
}

const filterDevices = (items: DeviceItem[], query: DeviceQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return items.filter((item) => {
    const matchesKeyword =
      !keyword ||
      item.name.toLowerCase().includes(keyword) ||
      item.udid.toLowerCase().includes(keyword) ||
      item.remark.toLowerCase().includes(keyword)
    const matchesEnabled = !query.enabledStatus || item.enabledStatus === query.enabledStatus
    const matchesRuntime = !query.runtimeStatus || item.runtimeStatus === query.runtimeStatus
    return matchesKeyword && matchesEnabled && matchesRuntime
  })
}

export const getDevicesApi = async (query: DeviceQuery): Promise<DeviceListResponse> => {
  if (USE_MOCK_API) {
    await wait(150)
    const filtered = filterDevices(readDevices(), query)
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<DeviceListResponse, DeviceListResponse>(API_ENDPOINTS.devices.list, {
    params: query,
  })
}

export const getDeviceOptionsApi = async (): Promise<DeviceItem[]> => {
  if (USE_MOCK_API) {
    await wait(100)
    return readDevices()
  }

  return request.get<DeviceItem[], DeviceItem[]>(API_ENDPOINTS.devices.options)
}

export const createDeviceApi = async (payload: DevicePayload): Promise<DeviceItem> => {
  if (USE_MOCK_API) {
    await wait(160)
    const devices = readDevices()
    const nextDevice: DeviceItem = {
      id: Math.max(0, ...devices.map((item) => item.id)) + 1,
      name: payload.name,
      udid: payload.udid,
      deviceModel: payload.deviceModel,
      systemPort: payload.systemPort,
      appiumServerUrl: payload.appiumPort ? `http://127.0.0.1:${payload.appiumPort}` : null,
      province: payload.province,
      remark: payload.remark,
      enabledStatus: 'enabled',
      runtimeStatus: 'offline',
      createdAt: now(),
      updatedAt: now(),
    }
    writeDevices([nextDevice, ...devices])
    return nextDevice
  }

  return request.post<DeviceItem, DeviceItem>(API_ENDPOINTS.devices.create, payload)
}

export const updateDeviceApi = async (id: number, payload: DevicePayload): Promise<DeviceItem> => {
  if (USE_MOCK_API) {
    await wait(160)
    const devices = readDevices()
    const nextDevices = devices.map((item) =>
      item.id === id
        ? {
            ...item,
            ...payload,
            appiumServerUrl: payload.appiumPort
              ? `http://127.0.0.1:${payload.appiumPort}`
              : null,
            updatedAt: now(),
          }
        : item,
    )
    writeDevices(nextDevices)
    const updated = nextDevices.find((item) => item.id === id)
    if (!updated) {
      throw new Error('设备不存在')
    }
    return updated
  }

  return request.put<DeviceItem, DeviceItem>(API_ENDPOINTS.devices.update(id), payload)
}

export const updateDeviceEnabledStatusApi = async (
  id: number,
  enabledStatus: DeviceEnabledStatus,
): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(140)
    writeDevices(
      readDevices().map((item) =>
        item.id === id ? { ...item, enabledStatus, updatedAt: now() } : item,
      ),
    )
    return
  }

  const action = enabledStatus === 'enabled' ? 'enable' : 'disable'
  return request.post<void, void>(
    action === 'enable' ? API_ENDPOINTS.devices.enable(id) : API_ENDPOINTS.devices.disable(id),
  )
}
