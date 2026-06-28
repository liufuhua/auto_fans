<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataAnalysis, Download, Refresh, Search } from '@element-plus/icons-vue'
import {
  exportAutomationResultsToDesktopApi,
  getAutomationResultsApi,
} from '../api/automationResults'
import {
  confirmCommentRecheckLoginApi,
  createCommentRecheckLoginSessionApi,
  getCommentRecheckLoginQrApi,
  getCommentRecheckLoginStatusApi,
  startCommentRecheckApi,
  startCommentRecheckByDateRangeApi,
  startTodayCommentRecheckApi,
} from '../api/commentRecheck'
import { getDailyTaskOptionsApi } from '../api/dailyTasks'
import { getDeviceOptionsApi } from '../api/devices'
import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from '../api/doctors'
import type {
  AutomationResultItem,
  AutomationResultStatus,
  CommentRecheckStatus,
} from '../types/automationResult'
import type { DailyTask } from '../types/dailyTask'
import type { DeviceItem } from '../types/device'
import type { DoctorItem, DoctorKeywordItem } from '../types/doctor'

const loading = ref(false)
const results = ref<AutomationResultItem[]>([])
const total = ref(0)
const tasks = ref<DailyTask[]>([])
const doctors = ref<DoctorItem[]>([])
const keywords = ref<DoctorKeywordItem[]>([])
const devices = ref<DeviceItem[]>([])
const resultDialogVisible = ref(false)
const selectedResult = ref<AutomationResultItem | null>(null)
const recheckLoading = ref(false)
const todayRecheckLoading = ref(false)
const rangeRecheckLoading = ref(false)
const exportLoading = ref(false)
const selectedRows = ref<AutomationResultItem[]>([])
const loginDialogVisible = ref(false)
const loginSessionLoading = ref(false)
const loginConfirming = ref(false)
const loginSessionId = ref('')
const loginQrObjectUrl = ref('')
const loginMessage = ref('')
const pendingAfterLogin = ref<(() => Promise<void>) | null>(null)
const exportDateRange = ref<[string, string] | null>(null)

const query = reactive({
  taskId: '' as number | '',
  doctorId: '' as number | '',
  keywordId: '' as number | '',
  deviceId: '' as number | '',
  status: '' as AutomationResultStatus | '',
  keyword: '',
  page: 1,
  pageSize: 50,
})

const statusText: Record<AutomationResultStatus, string> = {
  success: '成功',
  failed: '失败',
}

const getStatusText = (status: AutomationResultStatus) => statusText[status]

const recheckStatusText: Record<CommentRecheckStatus, string> = {
  not_checked: '未校验',
  queued: '已提交',
  checking: '校验中',
  exists: '评论存在',
  missing: '评论不存在',
  failed: '失败',
  login_required: '需要登录',
  captcha_required: '需要验证码',
}

const recheckStatusTagType: Record<CommentRecheckStatus, 'info' | 'success' | 'warning' | 'danger'> =
  {
    not_checked: 'info',
    queued: 'info',
    checking: 'info',
    exists: 'success',
    missing: 'warning',
    failed: 'danger',
    login_required: 'warning',
    captcha_required: 'warning',
  }

const getRecheckStatusText = (status?: CommentRecheckStatus) =>
  status ? recheckStatusText[status] : '未校验'

const getRecheckStatusTagType = (status?: CommentRecheckStatus) =>
  status ? recheckStatusTagType[status] : 'info'

const isRecheckable = (row: AutomationResultItem) =>
  row.status === 'success' &&
  Boolean(row.videoLink) &&
  row.commentRecheckStatus !== 'queued' &&
  row.commentRecheckStatus !== 'checking'

const recheckableRows = computed(() => results.value.filter((row) => isRecheckable(row)))

const selectedRecheckableRows = computed(() =>
  selectedRows.value.filter((row) => isRecheckable(row)),
)

const filteredKeywords = computed(() =>
  keywords.value.filter((keyword) => !query.doctorId || keyword.doctorId === query.doctorId),
)

const formatDateTime = (value?: string) => {
  if (!value) {
    return '-'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

const getTodayDateText = () =>
  new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())

const loadOptions = async () => {
  ;[tasks.value, doctors.value, keywords.value, devices.value] = await Promise.all([
    getDailyTaskOptionsApi(),
    getDoctorOptionsApi(),
    getDoctorKeywordOptionsApi(),
    getDeviceOptionsApi(),
  ])
}

const loadResults = async () => {
  loading.value = true
  try {
    const response = await getAutomationResultsApi(query)
    results.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const searchResults = () => {
  query.page = 1
  loadResults()
}

const resetQuery = () => {
  query.taskId = ''
  query.doctorId = ''
  query.keywordId = ''
  query.deviceId = ''
  query.status = ''
  query.keyword = ''
  query.page = 1
  loadResults()
}

const openResultSummary = (row: AutomationResultItem) => {
  selectedResult.value = row
  resultDialogVisible.value = true
}

const handleSelectionChange = (rows: AutomationResultItem[]) => {
  selectedRows.value = rows
}

const getRecheckTooltip = (row: AutomationResultItem) => {
  const parts = [row.commentRecheckFailReason || getRecheckStatusText(row.commentRecheckStatus)]
  if (row.commentRecheckCheckedAt) {
    parts.push(`校验时间：${formatDateTime(row.commentRecheckCheckedAt)}`)
  }
  return parts.join('\n')
}

const clearLoginQrObjectUrl = () => {
  if (loginQrObjectUrl.value) {
    URL.revokeObjectURL(loginQrObjectUrl.value)
    loginQrObjectUrl.value = ''
  }
}

const loadLoginQr = async (sessionId: string) => {
  clearLoginQrObjectUrl()
  const blob = await getCommentRecheckLoginQrApi(sessionId)
  loginQrObjectUrl.value = URL.createObjectURL(blob)
}

const openDouyinLoginDialog = async () => {
  loginSessionLoading.value = true
  try {
    const response = await createCommentRecheckLoginSessionApi()
    loginMessage.value = response.message || ''
    if (response.loggedIn) {
      loginDialogVisible.value = false
      return true
    }

    loginSessionId.value = response.sessionId || ''
    if (loginSessionId.value) {
      await loadLoginQr(loginSessionId.value)
    }
    loginDialogVisible.value = true
    return false
  } finally {
    loginSessionLoading.value = false
  }
}

const ensureDouyinLogin = async (afterLogin: () => Promise<void>) => {
  const status = await getCommentRecheckLoginStatusApi()
  if (status.loggedIn) {
    return true
  }

  pendingAfterLogin.value = afterLogin
  return await openDouyinLoginDialog()
}

const confirmDouyinLogin = async () => {
  loginConfirming.value = true
  try {
    const response = await confirmCommentRecheckLoginApi({
      sessionId: loginSessionId.value || undefined,
    })
    loginMessage.value = response.message || ''
    if (!response.loggedIn) {
      if (response.sessionId) {
        loginSessionId.value = response.sessionId
        await loadLoginQr(response.sessionId)
      }
      ElMessage.warning(response.message || '尚未检测到登录成功')
      return
    }

    ElMessage.success('抖音登录成功')
    loginDialogVisible.value = false
    clearLoginQrObjectUrl()
    const pendingAction = pendingAfterLogin.value
    pendingAfterLogin.value = null
    if (pendingAction) {
      await pendingAction()
    }
  } finally {
    loginConfirming.value = false
  }
}

const refreshDouyinLoginQr = async () => {
  await openDouyinLoginDialog()
}

const submitTodayCommentRecheck = async () => {
  const response = await startTodayCommentRecheckApi()
  if (response.loginRequired) {
    ElMessage.warning('抖音未登录，请先扫码登录')
  } else if (response.submitted > 0) {
    ElMessage.success(`已提交 ${response.submitted} 条评论校验`)
  } else {
    ElMessage.warning('今天没有可校验的成功结果或视频链接')
  }
  await loadResults()
}

const getExportDateRange = () => {
  if (!exportDateRange.value) {
    return null
  }
  const [startDate, endDate] = exportDateRange.value
  if (!startDate || !endDate) {
    return null
  }
  return { startDate, endDate }
}

const submitDateRangeCommentRecheck = async () => {
  const range = getExportDateRange()
  if (!range) {
    ElMessage.warning('请先选择校验日期范围')
    return
  }

  const response = await startCommentRecheckByDateRangeApi(range)
  if (response.loginRequired) {
    ElMessage.warning('抖音未登录，请先扫码登录')
  } else if (response.submitted > 0) {
    const skippedText = response.skipped ? `，跳过 ${response.skipped} 条` : ''
    ElMessage.success(`已提交 ${response.submitted} 条评论校验${skippedText}`)
  } else {
    ElMessage.warning('该日期范围内没有可校验的成功结果或视频链接')
  }
  await loadResults()
}

const submitSelectedCommentRecheck = async () => {
  const rows = selectedRecheckableRows.value
  if (!rows.length) {
    ElMessage.warning('请先选择可校验的成功结果')
    return
  }

  const response = await startCommentRecheckApi({
    ids: rows.map((row) => row.id),
  })
  if (response.loginRequired) {
    ElMessage.warning('抖音未登录，请先扫码登录')
  } else if (response.submitted > 0) {
    ElMessage.success(`已提交 ${response.submitted} 条评论校验`)
  } else {
    ElMessage.warning('所选结果没有可校验的视频链接')
  }
  await loadResults()
}

const startSelectedCommentRecheck = async () => {
  if (!selectedRecheckableRows.value.length) {
    ElMessage.warning('请先选择可校验的成功结果')
    return
  }

  recheckLoading.value = true
  try {
    const loggedIn = await ensureDouyinLogin(submitSelectedCommentRecheck)
    if (loggedIn) {
      await submitSelectedCommentRecheck()
    }
  } finally {
    recheckLoading.value = false
  }
}

const startTodayCommentRecheck = async () => {
  try {
    await ElMessageBox.confirm(
      '将对今天成功且有视频链接的执行结果发起评论校验，确认继续？',
      '评论校验',
      {
        confirmButtonText: '开始校验',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  todayRecheckLoading.value = true
  try {
    const loggedIn = await ensureDouyinLogin(submitTodayCommentRecheck)
    if (loggedIn) {
      await submitTodayCommentRecheck()
    }
  } finally {
    todayRecheckLoading.value = false
  }
}

const startDateRangeCommentRecheck = async () => {
  const range = getExportDateRange()
  if (!range) {
    ElMessage.warning('请先选择校验日期范围')
    return
  }

  try {
    await ElMessageBox.confirm(
      `将对 ${range.startDate} 至 ${range.endDate} 成功且有视频链接的执行结果发起评论校验，确认继续？`,
      '评论校验',
      {
        confirmButtonText: '开始校验',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  rangeRecheckLoading.value = true
  try {
    const loggedIn = await ensureDouyinLogin(submitDateRangeCommentRecheck)
    if (loggedIn) {
      await submitDateRangeCommentRecheck()
    }
  } finally {
    rangeRecheckLoading.value = false
  }
}

const exportResults = async () => {
  const range = getExportDateRange()
  if (!range) {
    ElMessage.warning('请先选择完整的导出日期范围')
    return
  }

  exportLoading.value = true
  try {
    const response = await exportAutomationResultsToDesktopApi(range.startDate, range.endDate)
    ElMessage.success(`已导出到桌面：${response.path}`)
  } finally {
    exportLoading.value = false
  }
}

const handlePageChange = (page: number) => {
  query.page = page
  loadResults()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadResults()
}

watch(
  () => query.doctorId,
  () => {
    query.keywordId = ''
  },
)

onMounted(async () => {
  const today = getTodayDateText()
  exportDateRange.value = [today, today]
  await loadOptions()
  await loadResults()
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">执行结果</h1>
        <p class="page-subtitle">查看评论发布账号、视频链接、执行状态和完整执行结果。</p>
      </div>
      <el-button
        :icon="DataAnalysis"
        :loading="recheckLoading"
        :disabled="!selectedRecheckableRows.length"
        type="primary"
        @click="startSelectedCommentRecheck"
      >
        校验选中
      </el-button>
      <el-button
        :icon="DataAnalysis"
        :loading="todayRecheckLoading"
        @click="startTodayCommentRecheck"
      >
        校验今日
      </el-button>
      <div class="export-actions">
        <el-date-picker
          v-model="exportDateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          range-separator="至"
          style="width: 260px"
        />
        <el-button :icon="Download" :loading="exportLoading" @click="exportResults">
          导出
        </el-button>
        <el-button
          :icon="DataAnalysis"
          :loading="rangeRecheckLoading"
          @click="startDateRangeCommentRecheck"
        >
          校验范围
        </el-button>
      </div>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="任务">
          <el-select
            v-model="query.taskId"
            clearable
            filterable
            placeholder="全部任务"
            style="width: 170px"
          >
            <el-option
              v-for="task in tasks"
              :key="task.id"
              :label="`${task.taskDate} #${task.id}`"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="医生">
          <el-select
            v-model="query.doctorId"
            clearable
            filterable
            placeholder="全部医生"
            style="width: 150px"
          >
            <el-option
              v-for="doctor in doctors"
              :key="doctor.id"
              :label="doctor.name"
              :value="doctor.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-select
            v-model="query.keywordId"
            clearable
            filterable
            placeholder="全部关键词"
            style="width: 170px"
          >
            <el-option
              v-for="keyword in filteredKeywords"
              :key="keyword.id"
              :label="keyword.keyword"
              :value="keyword.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="设备">
          <el-select
            v-model="query.deviceId"
            clearable
            filterable
            placeholder="全部设备"
            style="width: 150px"
          >
            <el-option
              v-for="device in devices"
              :key="device.id"
              :label="device.name"
              :value="device.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部状态" style="width: 120px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="评论 / 账号 / 失败原因"
            style="width: 220px"
            @keyup.enter="searchResults"
          />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchResults">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <div class="summary-strip">
        <span>已选择 {{ selectedRecheckableRows.length }} 条可校验结果</span>
        <span>当前页 {{ recheckableRows.length }} 条可校验</span>
      </div>

      <el-table
        v-loading="loading"
        :data="results"
        border
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="46" :selectable="isRecheckable" />
        <el-table-column label="任务" width="105">
          <template #default="{ row }">{{ row.taskDate }} #{{ row.taskId }}</template>
        </el-table-column>
        <el-table-column label="医生" width="90" prop="doctorName" />
        <el-table-column label="关键词" width="110" prop="keyword" />
        <el-table-column label="设备" width="90" prop="deviceName" />
        <el-table-column label="发布账号" width="110" prop="publishAccount" />
        <el-table-column label="评论内容" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">{{ row.commentContent }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" effect="plain">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="校验结果" width="100">
          <template #default="{ row }">
            <el-tooltip
              :content="getRecheckTooltip(row)"
              placement="top"
            >
              <el-tag :type="getRecheckStatusTagType(row.commentRecheckStatus)" effect="plain">
                {{ getRecheckStatusText(row.commentRecheckStatus) }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="校验时间" width="130">
          <template #default="{ row }">{{ formatDateTime(row.commentRecheckCheckedAt) }}</template>
        </el-table-column>
        <el-table-column label="详情" width="86">
          <template #default="{ row }">
            <el-button
              :disabled="!row.resultSummary"
              link
              type="primary"
              @click="openResultSummary(row)"
            >
              查看
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.failReason || '-' }}</template>
        </el-table-column>
        <el-table-column label="执行时间" width="150">
          <template #default="{ row }">
            <div class="time-cell">
              <span>{{ formatDateTime(row.startedAt) }}</span>
              <span>{{ formatDateTime(row.finishedAt) }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-footer">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          background
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50]"
          :total="total"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="resultDialogVisible" title="执行结果" width="640px">
      <div v-if="selectedResult" class="result-dialog-meta">
        {{ selectedResult.taskDate }} #{{ selectedResult.taskId }} /
        {{ selectedResult.doctorName }} /
        {{ selectedResult.keyword }} /
        {{ selectedResult.deviceName }}
      </div>
      <pre class="result-summary">{{ selectedResult?.resultSummary || '-' }}</pre>
    </el-dialog>

    <el-dialog
      v-model="loginDialogVisible"
      :close-on-click-modal="false"
      title="抖音扫码登录"
      width="420px"
      @closed="clearLoginQrObjectUrl"
    >
      <div class="login-dialog-body">
        <div v-loading="loginSessionLoading" class="qr-box">
          <img v-if="loginQrObjectUrl" :src="loginQrObjectUrl" alt="抖音登录二维码" />
          <span v-else>二维码加载中</span>
        </div>
        <div class="login-message">{{ loginMessage || '请使用抖音扫码登录' }}</div>
      </div>
      <template #footer>
        <el-button :loading="loginSessionLoading" @click="refreshDouyinLoginQr">刷新二维码</el-button>
        <el-button :loading="loginConfirming" type="primary" @click="confirmDouyinLogin">
          我已登录
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.filter-form {
  margin-bottom: 12px;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.summary-strip {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  padding: 10px 12px;
  color: #4b5563;
  font-size: 13px;
}

.export-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.time-cell {
  display: grid;
  gap: 2px;
  line-height: 1.35;
}

.result-dialog-meta {
  margin-bottom: 12px;
  color: #606266;
  font-size: 13px;
}

.result-summary {
  max-height: 520px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.6;
}

.login-dialog-body {
  display: grid;
  gap: 12px;
  justify-items: center;
}

.qr-box {
  display: grid;
  width: 260px;
  height: 260px;
  place-items: center;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  color: #606266;
}

.qr-box img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.login-message {
  color: #606266;
  font-size: 13px;
}
</style>
