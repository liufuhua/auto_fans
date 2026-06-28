<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  CircleCheck,
  CircleClose,
  CopyDocument,
  Plus,
  Refresh,
  Search,
  VideoPause,
  VideoPlay,
  View,
} from '@element-plus/icons-vue'
import {
  getAutomationServiceStatusApi,
  getAutomationRuntimeApi,
  startAutomationRuntimeApi,
  stopAutomationRuntimeApi,
} from '../api/automationRuntime'
import {
  createDailyTaskApi,
  dispatchDailyTaskApi,
  getDailyTaskDeviceDetailsApi,
  getDailyTasksApi,
  stopDailyTaskApi,
  updateDailyTaskItemSortOrderApi,
} from '../api/dailyTasks'
import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from '../api/doctors'
import type {
  DailyTask,
  DailyTaskConfigPayload,
  DailyTaskDeviceDetail,
  DailyTaskDevicePoolStatus,
  DailyTaskDispatchStatus,
  DailyTaskItem,
  DailyTaskStatus,
} from '../types/dailyTask'
import type { DoctorItem, DoctorKeywordItem } from '../types/doctor'
import type { AutomationRuntimeState, AutomationServiceInfo, AutomationServiceStatus } from '../types/automationRuntime'

type TaskConfigRow = DailyTaskConfigPayload & {
  rowId: number
  sortOrder: number
  keywordName?: string
  keywordUnavailable?: boolean
}

const loading = ref(false)
const tasks = ref<DailyTask[]>([])
const total = ref(0)
const doctors = ref<DoctorItem[]>([])
const keywords = ref<DoctorKeywordItem[]>([])
const dialogVisible = ref(false)
const detailDrawerVisible = ref(false)
const deviceDetailDrawerVisible = ref(false)
const deviceDetailLoading = ref(false)
const currentTask = ref<DailyTask | null>(null)
const currentDeviceDetailTask = ref<DailyTask | null>(null)
const deviceDetails = ref<DailyTaskDeviceDetail[]>([])
const taskFormRef = ref<FormInstance>()
const taskDialogTitle = ref('新建每日任务')
const taskSubmitText = ref('创建任务')
const runtimeLoading = ref(false)
const runtimeState = ref<AutomationRuntimeState | null>(null)
const serviceStatus = ref<AutomationServiceStatus | null>(null)
const maxTaskItemCount = 999
const draggingConfigRowId = ref<number | null>(null)
const configManualSortEditIds = ref<number[]>([])
const draggingDetailItemId = ref<number | null>(null)
const detailManualSortEditIds = ref<number[]>([])
const detailSortDirty = ref(false)
const detailSortSaving = ref(false)

const formatLocalDate = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const query = reactive({
  taskDate: '',
  status: '' as DailyTaskStatus | '',
  page: 1,
  pageSize: 50,
})

const taskForm = reactive({
  taskDate: formatLocalDate(new Date()),
  configs: [
    {
      rowId: Date.now(),
      sortOrder: 1,
      doctorId: '' as unknown as number,
      keywordId: '' as unknown as number,
      count: 1,
    },
  ] as TaskConfigRow[],
})

const taskRules: FormRules = {
  taskDate: [{ required: true, message: '请选择任务日期', trigger: 'change' }],
}

const statusText: Record<DailyTaskStatus, string> = {
  pending: '未开始',
  running: '执行中',
  completed: '已完成',
  stopped: '已停止',
  exception: '异常',
}

const statusTagType: Record<
  DailyTaskStatus,
  'info' | 'primary' | 'success' | 'warning' | 'danger'
> = {
  pending: 'info',
  running: 'primary',
  completed: 'success',
  stopped: 'warning',
  exception: 'danger',
}

const getStatusText = (status: DailyTaskStatus) => statusText[status]
const getStatusTagType = (status: DailyTaskStatus) => statusTagType[status]

const devicePoolStatusText: Record<DailyTaskDevicePoolStatus, string> = {
  pending: '未领取',
  claimed: '已领取',
  running: '已领取',
  success: '已完成',
  failed: '已失败',
  skipped: '已跳过',
}

const devicePoolStatusTagType: Record<
  DailyTaskDevicePoolStatus,
  'info' | 'primary' | 'success' | 'warning' | 'danger'
> = {
  pending: 'info',
  claimed: 'primary',
  running: 'primary',
  success: 'success',
  failed: 'danger',
  skipped: 'warning',
}

const getDevicePoolStatusText = (status: DailyTaskDevicePoolStatus) =>
  devicePoolStatusText[status] || status
const getDevicePoolStatusTagType = (status: DailyTaskDevicePoolStatus) =>
  devicePoolStatusTagType[status] || 'info'

const dispatchStatusText: Record<DailyTaskDispatchStatus, string> = {
  not_dispatched: '未分派',
  dispatching: '分派中',
  dispatched: '已分派',
  dispatch_failed: '分派失败',
}

const dispatchStatusTagType: Record<
  DailyTaskDispatchStatus,
  'info' | 'primary' | 'success' | 'warning' | 'danger'
> = {
  not_dispatched: 'info',
  dispatching: 'primary',
  dispatched: 'success',
  dispatch_failed: 'danger',
}

const getDispatchStatus = (status?: DailyTaskDispatchStatus) => status || 'not_dispatched'
const getDispatchStatusText = (status?: DailyTaskDispatchStatus) =>
  dispatchStatusText[getDispatchStatus(status)]
const getDispatchStatusTagType = (status?: DailyTaskDispatchStatus) =>
  dispatchStatusTagType[getDispatchStatus(status)]
const canDispatchTask = (task: DailyTask) =>
  task.status === 'pending' &&
  ['not_dispatched', 'dispatch_failed'].includes(getDispatchStatus(task.dispatchStatus))
const canSortTaskDetail = (task?: DailyTask | null) =>
  Boolean(
    task &&
      task.status === 'pending' &&
      ['not_dispatched', 'dispatch_failed'].includes(getDispatchStatus(task.dispatchStatus)),
  )
const businessRunning = computed(() => runtimeState.value?.businessStatus === 'running')
const serviceLabels: Record<string, string> = {
  api: 'API',
  web: 'Web',
  appium: 'Appium',
  client: '业务客户端',
}

const serviceRows = computed(() =>
  ['api', 'web', 'appium', 'client'].map((name) => ({
    name,
    label: serviceLabels[name],
    info: serviceStatus.value?.services[name],
  })),
)

const serviceTagType = (info?: AutomationServiceInfo) => (info?.status === 'running' ? 'success' : 'danger')
const serviceText = (info?: AutomationServiceInfo) => (info?.status === 'running' ? '正常' : '停止')
const serviceDetail = (info?: AutomationServiceInfo) => {
  if (!info) {
    return '-'
  }
  if (info.detail) {
    return info.detail
  }
  if (info.port) {
    return `${info.host || '127.0.0.1'}:${info.port}`
  }
  if (info.pid) {
    return `pid=${info.pid}`
  }
  return '-'
}

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

const progressText = (task: DailyTask) =>
  `${task.successCount + task.failedCount}/${task.totalCount}`
const progressPercentage = (task: DailyTask) =>
  task.totalCount ? Math.round(((task.successCount + task.failedCount) / task.totalCount) * 100) : 0

const availableKeywords = (row: TaskConfigRow) => {
  const activeKeywords = keywords.value.filter((keyword) => keyword.doctorId === row.doctorId)
  if (
    row.keywordUnavailable &&
    row.keywordId &&
    !activeKeywords.some((keyword) => keyword.id === row.keywordId)
  ) {
    return [
      ...activeKeywords,
      {
        id: row.keywordId,
        doctorId: row.doctorId,
        keyword: `${row.keywordName || '已删除关键词'}（已删除/停用）`,
        remark: '',
        status: 'deleted' as const,
        remainingCommentCount: 0,
        createdAt: '',
      },
    ]
  }
  return activeKeywords
}

const getDoctorProvince = (row: DailyTaskItem) =>
  row.doctorProvinces?.length ? row.doctorProvinces.join('、') : row.doctorProvince || '-'

const totalConfigCount = computed(() =>
  taskForm.configs.reduce((sum, config) => sum + Number(config.count || 0), 0),
)

const loadOptions = async () => {
  ;[doctors.value, keywords.value] = await Promise.all([
    getDoctorOptionsApi(),
    getDoctorKeywordOptionsApi(),
  ])
}

const loadTasks = async () => {
  loading.value = true
  try {
    const response = await getDailyTasksApi(query)
    tasks.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const loadRuntime = async () => {
  ;[runtimeState.value, serviceStatus.value] = await Promise.all([
    getAutomationRuntimeApi(),
    getAutomationServiceStatusApi(),
  ])
}

const searchTasks = () => {
  query.page = 1
  loadTasks()
}

const resetQuery = () => {
  query.taskDate = ''
  query.status = ''
  query.page = 1
  loadTasks()
}

const resetTaskForm = () => {
  taskForm.taskDate = formatLocalDate(new Date())
  taskForm.configs = [
    {
      rowId: Date.now(),
      sortOrder: 1,
      doctorId: '' as unknown as number,
      keywordId: '' as unknown as number,
      count: 1,
    },
  ]
}

const openCreateDialog = () => {
  taskDialogTitle.value = '新建每日任务'
  taskSubmitText.value = '创建任务'
  resetTaskForm()
  dialogVisible.value = true
  window.setTimeout(() => taskFormRef.value?.clearValidate(), 0)
}

const openCopyDialog = (task: DailyTask) => {
  taskDialogTitle.value = '复制每日任务'
  taskSubmitText.value = '保存任务'
  taskForm.taskDate = formatLocalDate(new Date())
  taskForm.configs = task.items.map((item, index) => ({
    rowId: Date.now() + index,
    sortOrder: item.sortOrder || index + 1,
    doctorId: item.doctorId,
    keywordId: item.keywordId,
    keywordName: item.keyword,
    keywordUnavailable: !keywords.value.some(
      (keyword) => keyword.id === item.keywordId && keyword.doctorId === item.doctorId,
    ),
    count: item.targetCount,
  }))
  dialogVisible.value = true
  window.setTimeout(() => taskFormRef.value?.clearValidate(), 0)
}

const toggleRuntime = async () => {
  runtimeLoading.value = true
  try {
    if (businessRunning.value) {
      await ElMessageBox.confirm(
        '确认停止业务？设备将停止领取新任务。',
        '停止业务',
        {
          confirmButtonText: '停止业务',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
      runtimeState.value = await stopAutomationRuntimeApi()
      ElMessage.success('业务已停止')
    } else {
      runtimeState.value = await startAutomationRuntimeApi()
      ElMessage.success('业务已启动')
    }
  } finally {
    runtimeLoading.value = false
  }
}

const addConfigRow = () => {
  taskForm.configs.push({
    rowId: Date.now() + Math.random(),
    sortOrder: taskForm.configs.length + 1,
    doctorId: '' as unknown as number,
    keywordId: '' as unknown as number,
    count: 1,
  })
}

const removeConfigRow = (rowId: number) => {
  if (taskForm.configs.length === 1) {
    ElMessage.warning('至少保留一行任务配置')
    return
  }
  taskForm.configs = taskForm.configs.filter((row) => row.rowId !== rowId)
  normalizeConfigSortOrders()
}

const handleDoctorChange = (row: TaskConfigRow) => {
  row.keywordId = '' as unknown as number
  row.keywordName = ''
  row.keywordUnavailable = false
}

const handleKeywordChange = (row: TaskConfigRow) => {
  const keyword = keywords.value.find((item) => item.id === row.keywordId)
  row.keywordName = keyword?.keyword || ''
  row.keywordUnavailable = false
}

const validateConfigs = () => {
  const invalidRow = taskForm.configs.find((row) => !row.doctorId || !row.keywordId || !row.count)
  if (invalidRow) {
    ElMessage.warning('请完整填写每一行的医生、关键词和条数')
    return false
  }

  if (taskForm.configs.some((row) => row.count < 1 || row.count > maxTaskItemCount)) {
    ElMessage.warning(`每行条数需要在 1 到 ${maxTaskItemCount} 之间`)
    return false
  }

  if (taskForm.configs.some((row) => row.keywordUnavailable)) {
    ElMessage.warning('任务配置中包含已删除或停用的关键词，请删除对应红色行后再保存')
    return false
  }

  return true
}

const configRowClassName = ({ row }: { row: TaskConfigRow }) =>
  row.keywordUnavailable ? 'config-row-warning' : ''

const normalizeConfigSortOrders = () => {
  taskForm.configs.forEach((row, index) => {
    row.sortOrder = index + 1
  })
}

const normalizeDetailSortOrders = () => {
  currentTask.value?.items.forEach((item, index) => {
    item.sortOrder = index + 1
  })
}

const targetIndexBySortOrder = (sortOrder: number, length: number) => {
  const targetIndex = Math.round(Number(sortOrder || 1)) - 1
  return Math.min(Math.max(targetIndex, 0), Math.max(length - 1, 0))
}

const applyConfigManualSortEdits = () => {
  const editedIds = [...configManualSortEditIds.value]
  for (const rowId of editedIds) {
    const fromIndex = taskForm.configs.findIndex((row) => row.rowId === rowId)
    if (fromIndex < 0) {
      continue
    }
    const [row] = taskForm.configs.splice(fromIndex, 1)
    taskForm.configs.splice(targetIndexBySortOrder(row.sortOrder || 1, taskForm.configs.length + 1), 0, row)
  }
  configManualSortEditIds.value = []
  normalizeConfigSortOrders()
}

const refreshConfigSortOrder = () => {
  if (configManualSortEditIds.value.length) {
    applyConfigManualSortEdits()
  } else {
    taskForm.configs.sort(
      (left, right) =>
        Number(left.sortOrder || 0) - Number(right.sortOrder || 0) ||
        left.rowId - right.rowId,
    )
    normalizeConfigSortOrders()
  }
}

const applyDetailManualSortEdits = () => {
  if (!currentTask.value) {
    return
  }
  const editedIds = [...detailManualSortEditIds.value]
  for (const itemId of editedIds) {
    const fromIndex = currentTask.value.items.findIndex((item) => item.id === itemId)
    if (fromIndex < 0) {
      continue
    }
    const [item] = currentTask.value.items.splice(fromIndex, 1)
    currentTask.value.items.splice(
      targetIndexBySortOrder(item.sortOrder || 1, currentTask.value.items.length + 1),
      0,
      item,
    )
  }
  detailManualSortEditIds.value = []
  normalizeDetailSortOrders()
}

const handleConfigSortChange = (row: TaskConfigRow) => {
  if (!configManualSortEditIds.value.includes(row.rowId)) {
    configManualSortEditIds.value.push(row.rowId)
  }
}

const handleDetailSortChange = (row: DailyTaskItem) => {
  detailSortDirty.value = true
  if (!detailManualSortEditIds.value.includes(row.id)) {
    detailManualSortEditIds.value.push(row.id)
  }
}

const handleConfigDragStart = (row: TaskConfigRow, event: DragEvent) => {
  draggingConfigRowId.value = row.rowId
  event.dataTransfer?.setData('text/plain', String(row.rowId))
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
}

const handleConfigDrop = (targetRow: TaskConfigRow) => {
  if (!draggingConfigRowId.value || draggingConfigRowId.value === targetRow.rowId) {
    draggingConfigRowId.value = null
    return
  }
  const fromIndex = taskForm.configs.findIndex((row) => row.rowId === draggingConfigRowId.value)
  const toIndex = taskForm.configs.findIndex((row) => row.rowId === targetRow.rowId)
  if (fromIndex < 0 || toIndex < 0) {
    draggingConfigRowId.value = null
    return
  }
  const [row] = taskForm.configs.splice(fromIndex, 1)
  taskForm.configs.splice(toIndex, 0, row)
  configManualSortEditIds.value = []
  normalizeConfigSortOrders()
  draggingConfigRowId.value = null
}

const handleDetailDragStart = (row: DailyTaskItem, event: DragEvent) => {
  draggingDetailItemId.value = row.id
  event.dataTransfer?.setData('text/plain', String(row.id))
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
}

const handleDetailDrop = (targetRow: DailyTaskItem) => {
  if (!currentTask.value || !draggingDetailItemId.value || draggingDetailItemId.value === targetRow.id) {
    draggingDetailItemId.value = null
    return
  }
  const fromIndex = currentTask.value.items.findIndex((item) => item.id === draggingDetailItemId.value)
  const toIndex = currentTask.value.items.findIndex((item) => item.id === targetRow.id)
  if (fromIndex < 0 || toIndex < 0) {
    draggingDetailItemId.value = null
    return
  }
  const [item] = currentTask.value.items.splice(fromIndex, 1)
  currentTask.value.items.splice(toIndex, 0, item)
  detailManualSortEditIds.value = []
  normalizeDetailSortOrders()
  detailSortDirty.value = true
  draggingDetailItemId.value = null
}

const submitTask = async () => {
  const valid = await taskFormRef.value?.validate().catch(() => false)
  if (!valid || !validateConfigs()) {
    return
  }
  if (configManualSortEditIds.value.length) {
    applyConfigManualSortEdits()
  } else {
    normalizeConfigSortOrders()
  }

  await createDailyTaskApi({
    taskDate: taskForm.taskDate,
    configs: taskForm.configs.map((row) => ({
      doctorId: row.doctorId,
      keywordId: row.keywordId,
      count: row.count,
      sortOrder: row.sortOrder,
    })),
  })
  ElMessage.success('每日任务已创建')
  dialogVisible.value = false
  query.taskDate = taskForm.taskDate
  query.page = 1
  loadTasks()
}

const stopTask = async (task: DailyTask) => {
  await ElMessageBox.confirm(`确认停止 ${task.taskDate} 的每日任务？`, '停止确认', {
    confirmButtonText: '停止任务',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await stopDailyTaskApi(task.id)
  ElMessage.success('任务已停止')
  loadTasks()
}

const dispatchTask = async (task: DailyTask) => {
  await ElMessageBox.confirm(`确认开始分派 ${task.taskDate} 的每日任务？`, '开始分派', {
    confirmButtonText: '开始分派',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await dispatchDailyTaskApi(task.id)
  loadTasks()
}

const openDetail = (task: DailyTask) => {
  currentTask.value = task
  detailManualSortEditIds.value = []
  detailSortDirty.value = false
  detailDrawerVisible.value = true
}

const openDeviceDetail = async (task: DailyTask) => {
  currentDeviceDetailTask.value = task
  deviceDetails.value = []
  deviceDetailDrawerVisible.value = true
  deviceDetailLoading.value = true
  try {
    const response = await getDailyTaskDeviceDetailsApi(task.id)
    deviceDetails.value = response.items
  } finally {
    deviceDetailLoading.value = false
  }
}

const saveDetailSortOrder = async () => {
  if (!currentTask.value) {
    return
  }
  if (detailManualSortEditIds.value.length) {
    applyDetailManualSortEdits()
  } else {
    normalizeDetailSortOrders()
  }

  detailSortSaving.value = true
  try {
    const updatedTask = await updateDailyTaskItemSortOrderApi(currentTask.value.id, {
      items: currentTask.value.items.map((item) => ({
        id: item.id,
        sortOrder: item.sortOrder,
      })),
    })
    currentTask.value = updatedTask
    tasks.value = tasks.value.map((task) => (task.id === updatedTask.id ? updatedTask : task))
    detailSortDirty.value = false
    ElMessage.success('任务明细排序已保存')
  } finally {
    detailSortSaving.value = false
  }
}

const handlePageChange = (page: number) => {
  query.page = page
  loadTasks()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadTasks()
}

onMounted(async () => {
  await Promise.all([loadOptions(), loadTasks(), loadRuntime()])
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">每日任务</h1>
        <p class="page-subtitle">每天手动创建医生、关键词和条数配置。</p>
      </div>
      <div class="toolbar-actions">
        <el-tag :type="businessRunning ? 'success' : 'info'" effect="plain">
          {{ businessRunning ? '业务运行中' : '业务未启动' }}
        </el-tag>
        <el-button
          :icon="businessRunning ? VideoPause : VideoPlay"
          :loading="runtimeLoading"
          :type="businessRunning ? 'warning' : 'success'"
          @click="toggleRuntime"
        >
          {{ businessRunning ? '停止业务' : '启动业务' }}
        </el-button>
        <el-button :icon="Refresh" @click="loadRuntime">刷新状态</el-button>
        <el-button :icon="Plus" type="primary" @click="openCreateDialog">新建任务</el-button>
      </div>
    </div>

    <div class="service-status-panel">
      <div
        v-for="service in serviceRows"
        :key="service.name"
        class="service-status-item"
      >
        <span class="service-status-name">{{ service.label }}</span>
        <el-tag :type="serviceTagType(service.info)" effect="plain">
          {{ serviceText(service.info) }}
        </el-tag>
        <span class="service-status-detail">{{ serviceDetail(service.info) }}</span>
      </div>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="任务日期">
          <el-date-picker
            v-model="query.taskDate"
            clearable
            placeholder="全部日期"
            type="date"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="query.status"
            clearable
            placeholder="全部状态"
            style="width: 140px"
          >
            <el-option
              v-for="(label, value) in statusText"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchTasks">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="tasks" border>
        <el-table-column label="任务ID" width="90" prop="id" />
        <el-table-column label="任务日期" min-width="120" prop="taskDate" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" effect="plain">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分派状态" width="110">
          <template #default="{ row }">
            <el-tag :type="getDispatchStatusTagType(row.dispatchStatus)" effect="plain">
              {{ getDispatchStatusText(row.dispatchStatus) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务进度" min-width="240">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress :percentage="progressPercentage(row)" />
              <span>{{ progressText(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="成功" width="80" prop="successCount" />
        <el-table-column label="失败" width="80" prop="failedCount" />
        <el-table-column label="总条数" width="90" prop="totalCount" />
        <el-table-column label="创建人" width="110" prop="createdBy" />
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column fixed="right" label="操作" width="250">
          <template #default="{ row }">
            <el-button :icon="View" link type="primary" @click="openDetail(row)">
              医生明细
            </el-button>
            <el-button :icon="View" link type="primary" @click="openDeviceDetail(row)">
              设备明细
            </el-button>
            <el-button :icon="CopyDocument" link type="primary" @click="openCopyDialog(row)">
              复制
            </el-button>
            <el-button
              v-if="canDispatchTask(row)"
              :icon="VideoPlay"
              link
              type="success"
              @click="dispatchTask(row)"
            >
              开始分派
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'running'"
              :icon="CircleClose"
              link
              type="danger"
              @click="stopTask(row)"
            >
              停止
            </el-button>
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

    <el-dialog v-model="dialogVisible" :title="taskDialogTitle" width="860px">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="92px">
        <el-form-item label="任务日期" prop="taskDate">
          <el-date-picker
            v-model="taskForm.taskDate"
            placeholder="请选择任务日期"
            type="date"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
      </el-form>

      <div class="config-header">
        <strong>任务配置</strong>
        <div class="config-actions">
          <el-button :icon="Refresh" @click="refreshConfigSortOrder">刷新排序</el-button>
          <el-button :icon="Plus" type="primary" @click="addConfigRow">添加配置行</el-button>
        </div>
      </div>

      <el-table :data="taskForm.configs" border :row-class-name="configRowClassName">
        <el-table-column label="顺序ID" width="118">
          <template #default="{ row }">
            <div
              class="sort-cell"
              @dragover.prevent
              @drop.prevent="handleConfigDrop(row)"
            >
              <button
                class="drag-handle"
                draggable="true"
                title="拖动排序"
                type="button"
                @dragend="draggingConfigRowId = null"
                @dragstart="handleConfigDragStart(row, $event)"
              >
                ⋮⋮
              </button>
              <el-input-number
                v-model="row.sortOrder"
                class="sort-input"
                :controls="false"
                :min="1"
                size="small"
                @change="handleConfigSortChange(row)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="医生" min-width="180">
          <template #default="{ row }">
            <el-select
              v-model="row.doctorId"
              filterable
              placeholder="请选择医生"
              style="width: 100%"
              @change="handleDoctorChange(row)"
            >
              <el-option
                v-for="doctor in doctors"
                :key="doctor.id"
                :label="doctor.name"
                :value="doctor.id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="关键词" min-width="210">
          <template #default="{ row }">
            <el-select
              v-model="row.keywordId"
              filterable
              placeholder="请选择关键词"
              style="width: 100%"
              @change="handleKeywordChange(row)"
            >
              <el-option
                v-for="keyword in availableKeywords(row)"
                :key="keyword.id"
                :label="keyword.keyword"
                :value="keyword.id"
                :disabled="keyword.status !== 'active'"
              />
            </el-select>
            <div v-if="row.keywordUnavailable" class="config-warning-text">
              该关键词已删除或停用，请删除此行
            </div>
          </template>
        </el-table-column>
        <el-table-column label="条数" width="160">
          <template #default="{ row }">
            <el-input-number
              v-model="row.count"
              :max="maxTaskItemCount"
              :min="1"
              controls-position="right"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeConfigRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="config-summary">
        合计 {{ totalConfigCount }} 条，将由可用设备主动领取执行。
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTask">{{ taskSubmitText }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailDrawerVisible" size="936px" title="医生明细">
      <template #header>
        <div>
          <strong>{{ currentTask?.taskDate }} 医生明细</strong>
          <p class="drawer-subtitle">
            总计 {{ currentTask?.totalCount || 0 }} 条，完成
            {{ currentTask ? progressText(currentTask) : '0/0' }}
          </p>
        </div>
      </template>

      <div
        v-if="canSortTaskDetail(currentTask)"
        class="detail-sort-toolbar"
      >
        <el-button
          :icon="CircleCheck"
          :loading="detailSortSaving"
          :type="detailSortDirty ? 'primary' : 'default'"
          @click="saveDetailSortOrder"
        >
          保存排序
        </el-button>
      </div>

      <el-table v-if="currentTask" :data="currentTask.items" border>
        <el-table-column label="顺序ID" width="118">
          <template #default="{ row }">
            <div
              v-if="canSortTaskDetail(currentTask)"
              class="sort-cell"
              @dragover.prevent
              @drop.prevent="handleDetailDrop(row)"
            >
              <button
                class="drag-handle"
                draggable="true"
                title="拖动排序"
                type="button"
                @dragend="draggingDetailItemId = null"
                @dragstart="handleDetailDragStart(row, $event)"
              >
                ⋮⋮
              </button>
              <el-input-number
                v-model="row.sortOrder"
                class="sort-input"
                :controls="false"
                :min="1"
                size="small"
                @change="handleDetailSortChange(row)"
              />
            </div>
            <span v-else>{{ row.sortOrder }}</span>
          </template>
        </el-table-column>
        <el-table-column label="医生" min-width="120" prop="doctorName" />
        <el-table-column label="省份" width="90">
          <template #default="{ row }">{{ getDoctorProvince(row) }}</template>
        </el-table-column>
        <el-table-column label="关键词" min-width="160" prop="keyword" />
        <el-table-column label="剩余评论数量" width="120">
          <template #default="{ row }">
            <span :class="{ 'remaining-count-zero': row.remainingCommentCount === 0 }">
              {{ row.remainingCommentCount }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="目标条数" width="100" prop="targetCount" />
        <el-table-column label="已分派" width="90">
          <template #default="{ row }">{{ row.dispatchedCount || 0 }}</template>
        </el-table-column>
        <el-table-column label="已领取" width="90" prop="claimedCount" />
        <el-table-column label="成功" width="80" prop="successCount" />
        <el-table-column label="失败" width="80" prop="failedCount" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" effect="plain">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="deviceDetailDrawerVisible" size="936px" title="设备明细">
      <template #header>
        <div>
          <strong>{{ currentDeviceDetailTask?.taskDate }} 设备明细</strong>
          <p class="drawer-subtitle">
            按设备查看已分派任务池，当前 {{ deviceDetails.length }} 台设备。
          </p>
        </div>
      </template>

      <el-table v-loading="deviceDetailLoading" :data="deviceDetails" border>
        <el-table-column type="expand" width="54">
          <template #default="{ row }">
            <el-table class="device-subtable" :data="row.tasks" border>
              <el-table-column label="医生昵称" min-width="140" prop="doctorName" />
              <el-table-column label="医生姓名" min-width="120">
                <template #default="{ row: taskRow }">
                  {{ taskRow.doctorRealName || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="关键字" min-width="150" prop="keyword" />
              <el-table-column label="评论内容" min-width="260" prop="commentContent" />
              <el-table-column label="状态" width="100">
                <template #default="{ row: taskRow }">
                  <el-tag :type="getDevicePoolStatusTagType(taskRow.status)" effect="plain">
                    {{ getDevicePoolStatusText(taskRow.status) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="设备名称" min-width="180" prop="deviceName" />
        <el-table-column label="设备省份" width="110">
          <template #default="{ row }">
            {{ row.deviceProvince || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="分派任务数" width="110" prop="assignedCount" />
        <el-table-column label="领取数量" width="100" prop="claimedCount" />
        <el-table-column label="完成数量" width="100" prop="successCount" />
        <el-table-column label="失败数量" width="100" prop="failedCount" />
      </el-table>
    </el-drawer>
  </section>
</template>

<style scoped>
.filter-form {
  margin-bottom: 12px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.service-status-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.service-status-item {
  display: grid;
  min-height: 72px;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  padding: 12px;
}

.service-status-name {
  color: #111827;
  font-weight: 600;
}

.service-status-detail {
  grid-column: 1 / -1;
  color: #6b7280;
  font-size: 12px;
}

@media (max-width: 960px) {
  .service-status-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.progress-cell {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 48px;
  align-items: center;
  gap: 10px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0 12px;
}

.config-actions {
  display: flex;
  gap: 8px;
}

.config-warning-text {
  margin-top: 4px;
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.3;
}

:deep(.config-row-warning) {
  --el-table-tr-bg-color: #fff1f0;
}

.config-summary {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  padding: 10px 12px;
  color: #4b5563;
  font-size: 13px;
}

.detail-sort-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.sort-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.drag-handle {
  width: 24px;
  height: 24px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #f9fafb;
  color: #6b7280;
  cursor: grab;
  line-height: 1;
}

.drag-handle:active {
  cursor: grabbing;
}

.sort-input {
  width: 58px;
}

.drawer-subtitle {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.remaining-count-zero {
  color: #f56c6c;
  font-weight: 600;
}

.device-subtable {
  margin: 8px 0;
}
</style>
