import type {
  AutomationTimingSettingItem,
  AutomationTimingSettingsPayload,
} from '../types/automationTiming'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

export const getAutomationTimingSettingsApi = async (): Promise<AutomationTimingSettingItem[]> => {
  return request.get<AutomationTimingSettingItem[], AutomationTimingSettingItem[]>(
    API_ENDPOINTS.automationTiming.list,
  )
}

export const updateAutomationTimingSettingsApi = async (
  payload: AutomationTimingSettingsPayload,
): Promise<AutomationTimingSettingItem[]> => {
  return request.put<AutomationTimingSettingItem[], AutomationTimingSettingItem[]>(
    API_ENDPOINTS.automationTiming.update,
    payload,
  )
}

export const resetAutomationTimingSettingsApi = async (): Promise<AutomationTimingSettingItem[]> => {
  return request.post<AutomationTimingSettingItem[], AutomationTimingSettingItem[]>(
    API_ENDPOINTS.automationTiming.resetDefaults,
  )
}
