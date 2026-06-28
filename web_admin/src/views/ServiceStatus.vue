<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getAutomationServiceStatusApi } from '../api/automationRuntime'
import type { AutomationServiceInfo, AutomationServiceStatus } from '../types/automationRuntime'

const loading = ref(false)
const status = ref<AutomationServiceStatus | null>(null)

const serviceLabels: Record<string, string> = {
  api: '后端 API',
  web: '前端页面',
  client: '业务客户端',
}

const serviceRows = computed(() =>
  ['api', 'web', 'client'].map((name) => ({
    name,
    label: serviceLabels[name],
    info: status.value?.services[name],
  })),
)

const appiumRows = computed(() => status.value?.appiumServers || [])

const appiumRunningCount = computed(
  () => appiumRows.value.filter((item) => item.status === 'running').length,
)

const appiumSummary = computed(() => status.value?.services.appium)

const runningCount = computed(
  () => serviceRows.value.filter((item) => item.info?.status === 'running').length,
)

const totalServiceCount = computed(() => serviceRows.value.length + appiumRows.value.length)

const totalRunningCount = computed(() => runningCount.value + appiumRunningCount.value)

const allRunning = computed(
  () => totalServiceCount.value > 0 && totalRunningCount.value === totalServiceCount.value,
)

const serviceTagType = (info?: AutomationServiceInfo) =>
  info?.status === 'running' ? 'success' : 'danger'

const serviceText = (info?: AutomationServiceInfo) =>
  info?.status === 'running' ? '运行中' : '已停止'

const serviceEndpoint = (info?: AutomationServiceInfo) => {
  if (!info) {
    return '-'
  }
  if (info.port) {
    return `${info.host || '127.0.0.1'}:${info.port}`
  }
  if (info.pid) {
    return `pid=${info.pid}`
  }
  return '-'
}

const appiumEndpoint = (info: AutomationServiceInfo) =>
  info.port ? `${info.host || '127.0.0.1'}:${info.port}` : '-'

const loadStatus = async () => {
  loading.value = true
  try {
    status.value = await getAutomationServiceStatusApi()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadStatus()
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">服务状态</h1>
        <p class="page-subtitle">查看桌面客户端启动的本地服务是否正常运行。</p>
      </div>
      <div class="toolbar-actions">
        <el-tag :type="allRunning ? 'success' : 'danger'" effect="plain">
          {{ totalRunningCount }}/{{ totalServiceCount }} 正常
        </el-tag>
        <el-button :icon="Refresh" :loading="loading" @click="loadStatus">刷新</el-button>
      </div>
    </div>

    <div class="service-grid">
      <div v-for="service in serviceRows" :key="service.name" class="service-card">
        <div class="service-card-header">
          <strong>{{ service.label }}</strong>
          <el-tag :type="serviceTagType(service.info)" effect="plain">
            {{ serviceText(service.info) }}
          </el-tag>
        </div>
        <dl>
          <div>
            <dt>地址</dt>
            <dd>{{ serviceEndpoint(service.info) }}</dd>
          </div>
          <div>
            <dt>进程</dt>
            <dd>{{ service.info?.pid || '-' }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ status?.updatedAt || '-' }}</dd>
          </div>
        </dl>
      </div>
    </div>

    <div class="appium-section">
      <div class="section-heading">
        <div>
          <h2>Appium 服务</h2>
          <p>{{ appiumSummary?.detail || `${appiumRunningCount}/${appiumRows.length} running` }}</p>
        </div>
        <el-tag :type="serviceTagType(appiumSummary)" effect="plain">
          {{ serviceText(appiumSummary) }}
        </el-tag>
      </div>
      <el-table :data="appiumRows" border>
        <el-table-column label="设备" min-width="130">
          <template #default="{ row }">{{ row.deviceName || row.name }}</template>
        </el-table-column>
        <el-table-column label="ADB UDID" min-width="190">
          <template #default="{ row }">{{ row.udid || '-' }}</template>
        </el-table-column>
        <el-table-column label="Appium 地址" min-width="160">
          <template #default="{ row }">{{ appiumEndpoint(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="serviceTagType(row)" effect="plain">
              {{ serviceText(row) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped>
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.service-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.service-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 16px;
}

.service-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.service-card dl {
  display: grid;
  gap: 10px;
  margin: 16px 0 0;
}

.service-card dl div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 10px;
}

.service-card dt {
  color: #6b7280;
  font-size: 13px;
}

.service-card dd {
  min-width: 0;
  margin: 0;
  color: #111827;
  font-size: 13px;
  word-break: break-all;
}

.appium-section {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 16px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.section-heading h2 {
  margin: 0;
  color: #111827;
  font-size: 16px;
}

.section-heading p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

@media (max-width: 900px) {
  .service-grid {
    grid-template-columns: 1fr;
  }
}
</style>
