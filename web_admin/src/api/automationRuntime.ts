import { API_ENDPOINTS } from './endpoints'
import { request } from './request'
import type { AutomationRuntimeState, AutomationServiceStatus } from '../types/automationRuntime'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const RUNTIME_KEY = 'douyin_auto_mock_automation_runtime'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const now = () => new Date().toISOString()

const defaultRuntime = (): AutomationRuntimeState => ({
  businessStatus: 'stopped',
  startedAt: null,
  stoppedAt: null,
  updatedAt: now(),
  remark: '',
})

const readRuntime = (): AutomationRuntimeState => {
  const raw = localStorage.getItem(RUNTIME_KEY)
  if (!raw) {
    const runtime = defaultRuntime()
    localStorage.setItem(RUNTIME_KEY, JSON.stringify(runtime))
    return runtime
  }
  try {
    return JSON.parse(raw) as AutomationRuntimeState
  } catch {
    const runtime = defaultRuntime()
    localStorage.setItem(RUNTIME_KEY, JSON.stringify(runtime))
    return runtime
  }
}

const writeRuntime = (runtime: AutomationRuntimeState) => {
  localStorage.setItem(RUNTIME_KEY, JSON.stringify(runtime))
}

export const getAutomationRuntimeApi = async (): Promise<AutomationRuntimeState> => {
  if (USE_MOCK_API) {
    await wait(80)
    return readRuntime()
  }

  return request.get<AutomationRuntimeState, AutomationRuntimeState>(
    API_ENDPOINTS.automationRuntime.state,
  )
}

export const getAutomationServiceStatusApi = async (): Promise<AutomationServiceStatus> => {
  if (USE_MOCK_API) {
    await wait(80)
    return {
      updatedAt: now(),
      services: {
        api: { name: 'api', status: 'running', host: '127.0.0.1', port: 8000 },
        web: { name: 'web', status: 'running', host: '127.0.0.1', port: 5173 },
        appium: { name: 'appium', status: 'stopped', detail: '1/2 running' },
        client: { name: 'client', status: 'stopped' },
      },
      appiumServers: [
        {
          name: 'appium_4721',
          status: 'running',
          host: '127.0.0.1',
          port: 4721,
          deviceName: 'device_01',
          udid: 'emulator-5554',
        },
        {
          name: 'appium_4722',
          status: 'stopped',
          host: '127.0.0.1',
          port: 4722,
          deviceName: 'device_02',
          udid: 'emulator-5556',
        },
      ],
    }
  }

  return request.get<AutomationServiceStatus, AutomationServiceStatus>(
    API_ENDPOINTS.automationRuntime.services,
  )
}

export const startAutomationRuntimeApi = async (): Promise<AutomationRuntimeState> => {
  if (USE_MOCK_API) {
    await wait(120)
    const runtime: AutomationRuntimeState = {
      ...readRuntime(),
      businessStatus: 'running',
      startedAt: now(),
      stoppedAt: null,
      updatedAt: now(),
      remark: 'admin start',
    }
    writeRuntime(runtime)
    return runtime
  }

  return request.post<AutomationRuntimeState, AutomationRuntimeState>(
    API_ENDPOINTS.automationRuntime.start,
    { remark: 'admin start' },
  )
}

export const stopAutomationRuntimeApi = async (): Promise<AutomationRuntimeState> => {
  if (USE_MOCK_API) {
    await wait(120)
    const runtime: AutomationRuntimeState = {
      ...readRuntime(),
      businessStatus: 'stopped',
      stoppedAt: now(),
      updatedAt: now(),
      remark: 'admin stop',
    }
    writeRuntime(runtime)
    return runtime
  }

  return request.post<AutomationRuntimeState, AutomationRuntimeState>(
    API_ENDPOINTS.automationRuntime.stop,
    { remark: 'admin stop' },
  )
}
