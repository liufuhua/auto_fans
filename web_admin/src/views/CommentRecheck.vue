<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, VideoPlay } from '@element-plus/icons-vue'
import {
  getCommentRecheckApi,
  startCommentRecheckApi,
  startCommentRecheckByDateRangeApi,
  startTodayCommentRecheckApi,
} from '../api/commentRecheck'
import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from '../api/doctors'
import type { CommentRecheckItem, CommentRecheckStatus } from '../types/commentRecheck'
import type { DoctorItem, DoctorKeywordItem } from '../types/doctor'

const loading = ref(false)
const rechecking = ref(false)
const records = ref<CommentRecheckItem[]>([])
const selectedRows = ref<CommentRecheckItem[]>([])
const doctors = ref<DoctorItem[]>([])
const keywords = ref<DoctorKeywordItem[]>([])
const total = ref(0)
const dateRange = ref<[string, string] | null>(null)

const query = reactive({
  doctorId: '' as number | '',
  keywordId: '' as number | '',
  status: '' as CommentRecheckStatus | '',
  keyword: '',
  page: 1,
  pageSize: 50,
})

const statusText: Record<CommentRecheckStatus, string> = {
  not_checked: '未校验',
  queued: '已提交',
  checking: '校验中',
  exists: '评论存在',
  missing: '评论不存在',
  failed: '复检失败',
  login_required: '需要登录',
  captcha_required: '需要验证码',
}

const statusTagType: Record<CommentRecheckStatus, 'info' | 'success' | 'warning' | 'danger'> = {
  not_checked: 'info',
  queued: 'info',
  checking: 'info',
  exists: 'success',
  missing: 'warning',
  failed: 'danger',
  login_required: 'warning',
  captcha_required: 'warning',
}

const filteredKeywords = computed(() =>
  keywords.value.filter((keyword) => !query.doctorId || keyword.doctorId === query.doctorId),
)

const getStatusText = (status: CommentRecheckStatus) => statusText[status]
const getStatusTagType = (status: CommentRecheckStatus) => statusTagType[status]

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

const loadOptions = async () => {
  ;[doctors.value, keywords.value] = await Promise.all([
    getDoctorOptionsApi(),
    getDoctorKeywordOptionsApi(),
  ])
}

const loadRecords = async () => {
  loading.value = true
  try {
    const response = await getCommentRecheckApi({
      ...query,
      startDate: dateRange.value?.[0],
      endDate: dateRange.value?.[1],
    })
    records.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const searchRecords = () => {
  query.page = 1
  loadRecords()
}

const resetQuery = () => {
  query.doctorId = ''
  query.keywordId = ''
  query.status = ''
  query.keyword = ''
  query.page = 1
  dateRange.value = null
  loadRecords()
}

const handleSelectionChange = (rows: CommentRecheckItem[]) => {
  selectedRows.value = rows
}

const startRecheck = async () => {
  if (!selectedRows.value.length) {
    ElMessage.warning('请先选择需要复检的评论记录')
    return
  }

  await ElMessageBox.confirm(`确认复检已选 ${selectedRows.value.length} 条评论？`, '复检确认', {
    confirmButtonText: '发起复检',
    cancelButtonText: '取消',
    type: 'warning',
  })

  rechecking.value = true
  try {
    const response = await startCommentRecheckApi({
      ids: selectedRows.value.map((row) => row.id),
    })
    if (response.loginRequired) {
      ElMessage.warning('抖音未登录，请先扫码登录')
    } else {
      ElMessage.success(`已提交复检：${response.submitted} 条`)
    }
    await loadRecords()
  } finally {
    rechecking.value = false
  }
}

const submitResponseMessage = (response: { submitted: number; skipped: number; loginRequired: boolean }) => {
  if (response.loginRequired) {
    ElMessage.warning('抖音未登录，请先扫码登录')
    return
  }
  if (response.submitted === 0) {
    ElMessage.info('没有可提交的复检记录')
    return
  }
  const skippedText = response.skipped ? `，跳过 ${response.skipped} 条` : ''
  ElMessage.success(`已提交复检：${response.submitted} 条${skippedText}`)
}

const startTodayRecheck = async () => {
  await ElMessageBox.confirm('确认复检今天的执行结果？', '今日复检确认', {
    confirmButtonText: '发起复检',
    cancelButtonText: '取消',
    type: 'warning',
  })

  rechecking.value = true
  try {
    const response = await startTodayCommentRecheckApi()
    submitResponseMessage(response)
    await loadRecords()
  } finally {
    rechecking.value = false
  }
}

const startDateRangeRecheck = async () => {
  if (!dateRange.value) {
    ElMessage.warning('请先选择任务日期范围')
    return
  }
  const [startDate, endDate] = dateRange.value
  if (!startDate || !endDate) {
    ElMessage.warning('请先选择完整的任务日期范围')
    return
  }

  await ElMessageBox.confirm(
    `确认复检 ${startDate} 至 ${endDate} 的执行结果？`,
    '日期范围复检确认',
    {
      confirmButtonText: '发起复检',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )

  rechecking.value = true
  try {
    const response = await startCommentRecheckByDateRangeApi({ startDate, endDate })
    submitResponseMessage(response)
    await loadRecords()
  } finally {
    rechecking.value = false
  }
}

const openVideo = (url?: string) => {
  if (!url) {
    ElMessage.info('评论视频链接为空')
    return
  }
  window.open(url, '_blank')
}

const handlePageChange = (page: number) => {
  query.page = page
  loadRecords()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadRecords()
}

watch(
  () => query.doctorId,
  () => {
    query.keywordId = ''
  },
)

onMounted(async () => {
  await loadOptions()
  await loadRecords()
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">评论复检</h1>
        <p class="page-subtitle">多选已完成评论，通过浏览器解析确认评论是否仍存在。</p>
      </div>
      <div class="toolbar-actions">
        <el-button :loading="rechecking" @click="startTodayRecheck">今日复检</el-button>
        <el-button :icon="VideoPlay" :loading="rechecking" type="primary" @click="startRecheck">
          发起复检
        </el-button>
      </div>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
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
        <el-form-item label="复检状态">
          <el-select v-model="query.status" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="未校验" value="not_checked" />
            <el-option label="已提交" value="queued" />
            <el-option label="校验中" value="checking" />
            <el-option label="评论存在" value="exists" />
            <el-option label="评论不存在" value="missing" />
            <el-option label="复检失败" value="failed" />
            <el-option label="需要登录" value="login_required" />
            <el-option label="需要验证码" value="captcha_required" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="评论 / 账号 / 失败原因"
            style="width: 240px"
            @keyup.enter="searchRecords"
          />
        </el-form-item>
        <el-form-item label="任务日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            range-separator="至"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchRecords">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
          <el-button :loading="rechecking" type="success" @click="startDateRangeRecheck">
            范围复检
          </el-button>
        </el-form-item>
      </el-form>

      <div class="summary-strip">
        <span>已选择 {{ selectedRows.length }} 条</span>
        <span>共 {{ total }} 条可复检评论</span>
      </div>

      <el-table
        v-loading="loading"
        :data="records"
        border
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column label="任务" width="105">
          <template #default="{ row }">{{ row.taskDate }} #{{ row.taskId }}</template>
        </el-table-column>
        <el-table-column label="医生" width="90" prop="doctorName" />
        <el-table-column label="关键词" width="110" prop="keyword" />
        <el-table-column label="设备" width="90" prop="deviceName" />
        <el-table-column label="发布账号" width="110" prop="publishAccount" />
        <el-table-column label="评论内容" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ row.commentContent }}</template>
        </el-table-column>
        <el-table-column label="复检状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" effect="plain">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复检时间" width="130">
          <template #default="{ row }">{{ formatDateTime(row.checkedAt) }}</template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.failReason || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="86">
          <template #default="{ row }">
            <el-button link type="primary" @click="openVideo(row.videoLink)">打开</el-button>
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

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}
</style>
