export type AutomationTimingSettingItem = {
  id: number
  key: string
  label: string
  minSeconds: number
  maxSeconds: number
  createdAt: string
  updatedAt: string
  timeValue?: string
}

export type AutomationTimingSettingPayload = {
  key: string
  minSeconds: number
  maxSeconds: number
}

export type AutomationTimingSettingsPayload = {
  items: AutomationTimingSettingPayload[]
}
