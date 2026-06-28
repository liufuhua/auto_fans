export type AutomationBusinessStatus = 'running' | 'stopped'

export type AutomationRuntimeState = {
  businessStatus: AutomationBusinessStatus
  startedAt?: string | null
  stoppedAt?: string | null
  updatedAt?: string | null
  remark: string
}

export type AutomationServiceState = 'running' | 'stopped'

export type AutomationServiceInfo = {
  name: string
  status: AutomationServiceState
  host?: string | null
  port?: number | null
  pid?: number | null
  detail?: string
  deviceName?: string | null
  udid?: string | null
}

export type AutomationServiceStatus = {
  updatedAt: string
  services: Record<string, AutomationServiceInfo>
  appiumServers: AutomationServiceInfo[]
}
