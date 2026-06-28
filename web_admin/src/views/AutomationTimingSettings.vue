<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Refresh, Select } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAutomationTimingSettingsApi,
  resetAutomationTimingSettingsApi,
  updateAutomationTimingSettingsApi,
} from '../api/automationTiming'
import type { AutomationTimingSettingItem } from '../types/automationTiming'

const loading = ref(false)
const saving = ref(false)
const resetLoading = ref(false)
const settings = ref<AutomationTimingSettingItem[]>([])
const singleValueSettingKeys = new Set([
  'single_device_daily_task_limit',
  'runtime_start_time',
  'runtime_end_time',
  'douyin_restart_interval',
])
const timeSettingKeys = new Set(['runtime_start_time', 'runtime_end_time'])

const isSingleValueSetting = (key: string) => singleValueSettingKeys.has(key)
const isTimeSetting = (key: string) => timeSettingKeys.has(key)
const isRestartIntervalSetting = (key: string) => key === 'douyin_restart_interval'

const singleValueMin = (_key: string) => 0
const singleValueMax = (_key: string) => undefined
const singleValuePrecision = (_key: string) => 0

const valueColumnLabel = (key: string) => {
  if (isTimeSetting(key)) {
    return ''
  }
  if (isRestartIntervalSetting(key)) {
    return '分钟'
  }
  if (key === 'single_device_daily_task_limit') {
    return '配置值'
  }
  return '最大时间（秒）'
}

const minuteToTimeText = (value: number) => {
  const normalized = ((Math.trunc(value) % 1440) + 1440) % 1440
  const hour = Math.floor(normalized / 60)
  const minute = normalized % 60
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

const timeTextToMinute = (value: string) => {
  const [hourText, minuteText] = value.split(':')
  const hour = Number(hourText)
  const minute = Number(minuteText)
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) {
    return null
  }
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return null
  }
  return hour * 60 + minute
}

const rowHint = (row: AutomationTimingSettingItem) => {
  if (row.key === 'single_device_daily_task_limit') {
    return '达到该值后，当天该设备不再领取新任务；0 表示不限制'
  }
  if (row.key === 'runtime_start_time') {
    return '每天从该时间点开始允许领取任务'
  }
  if (row.key === 'runtime_end_time') {
    return '每天到该时间点停止领取新任务；早于开始时间表示跨天'
  }
  if (row.key === 'douyin_restart_interval') {
    return '强制退出抖音后，等待该分钟数再继续重启或重连'
  }
  return row.minSeconds === row.maxSeconds ? '固定等待' : '在最小和最大时间之间随机等待'
}

const loadData = async () => {
  loading.value = true
  try {
    settings.value = (await getAutomationTimingSettingsApi()).map((item) => ({
      ...item,
      timeValue: isTimeSetting(item.key) ? minuteToTimeText(item.maxSeconds) : undefined,
    }))
  } finally {
    loading.value = false
  }
}

const validateRows = () => {
  for (const item of settings.value) {
    if (isSingleValueSetting(item.key)) {
      if (isTimeSetting(item.key)) {
        const minute = timeTextToMinute(item.timeValue || '')
        if (minute === null) {
          ElMessage.warning(`${item.label} 请选择有效时间`)
          return false
        }
        item.minSeconds = minute
        item.maxSeconds = minute
        continue
      }
      if (item.maxSeconds < 0) {
        ElMessage.warning(`${item.label} 不能小于 0`)
        return false
      }
      item.minSeconds = item.maxSeconds
      continue
    }
    if (item.minSeconds < 0 || item.maxSeconds < 0) {
      ElMessage.warning(`${item.label} 的时间不能小于 0`)
      return false
    }
    if (item.minSeconds > item.maxSeconds) {
      ElMessage.warning(`${item.label} 的最小时间不能大于最大时间`)
      return false
    }
  }
  return true
}

const saveSettings = async () => {
  if (!validateRows()) {
    return
  }
  saving.value = true
  try {
    settings.value = await updateAutomationTimingSettingsApi({
      items: settings.value.map((item) => ({
        key: item.key,
        minSeconds: isSingleValueSetting(item.key)
          ? Number(item.maxSeconds)
          : Number(item.minSeconds),
        maxSeconds: Number(item.maxSeconds),
      })),
    })
    ElMessage.success('配置已保存')
  } finally {
    saving.value = false
  }
}

const resetDefaults = async () => {
  await ElMessageBox.confirm('确认恢复默认配置？当前手动调整会被覆盖。', '恢复默认', {
    type: 'warning',
    confirmButtonText: '恢复默认',
    cancelButtonText: '取消',
  })
  resetLoading.value = true
  try {
    settings.value = await resetAutomationTimingSettingsApi()
    ElMessage.success('已恢复默认配置')
  } finally {
    resetLoading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">配置管理</h1>
        <p class="page-subtitle">配置主流程等待时间、单设备每日任务量等业务参数。</p>
      </div>
      <div class="toolbar-actions">
        <el-button :icon="Refresh" :loading="resetLoading" @click="resetDefaults">恢复默认</el-button>
        <el-button :icon="Select" :loading="saving" type="primary" @click="saveSettings">
          保存设置
        </el-button>
      </div>
    </div>

    <div class="content-panel">
      <el-table v-loading="loading" :data="settings" border>
        <el-table-column label="执行阶段" min-width="220" prop="label" />
        <el-table-column label="配置键" min-width="190" prop="key" />
        <el-table-column label="最小时间（秒）" width="180">
          <template #default="{ row }">
            <el-input-number
              v-if="!isSingleValueSetting(row.key)"
              v-model="row.minSeconds"
              :controls="false"
              :min="0"
              :precision="2"
              class="time-input"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="最大时间/配置值" width="180">
          <template #default="{ row }">
            <div class="value-cell">
              <el-time-picker
                v-if="isTimeSetting(row.key)"
                v-model="row.timeValue"
                class="time-picker"
                format="HH:mm"
                placeholder="选择时间"
                value-format="HH:mm"
              />
              <el-input-number
                v-else
                v-model="row.maxSeconds"
                :controls="false"
                :max="singleValueMax(row.key)"
                :min="singleValueMin(row.key)"
                :precision="isSingleValueSetting(row.key) ? singleValuePrecision(row.key) : 2"
                class="time-input"
              />
              <span class="value-unit">{{ valueColumnLabel(row.key) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="260">
          <template #default="{ row }">
            <span class="hint-text">{{ rowHint(row) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped>
.toolbar-actions {
  display: flex;
  gap: 10px;
}

.time-input {
  width: 132px;
}

.time-picker {
  width: 132px;
}

.value-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.value-unit {
  color: #606266;
  font-size: 13px;
  white-space: nowrap;
}

.hint-text {
  color: #606266;
}
</style>
