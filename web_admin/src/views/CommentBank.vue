<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules,
  type UploadFile,
} from 'element-plus'
import { Delete, Download, Refresh, Search, Upload } from '@element-plus/icons-vue'
import {
  batchDeleteCommentBankItemsApi,
  deleteCommentBankItemApi,
  getCommentBankApi,
  importCommentBankExcelApi,
} from '../api/commentBank'
import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from '../api/doctors'
import type { CommentBankItem, CommentUsageStatus } from '../types/commentBank'
import type { DoctorItem, DoctorKeywordItem } from '../types/doctor'

const loading = ref(false)
const comments = ref<CommentBankItem[]>([])
const selectedRows = ref<CommentBankItem[]>([])
const doctors = ref<DoctorItem[]>([])
const keywordOptions = ref<DoctorKeywordItem[]>([])
const total = ref(0)
const importDialogVisible = ref(false)
const importLoading = ref(false)
const importFormRef = ref<FormInstance>()
const selectedFile = ref<File | null>(null)

const query = reactive({
  doctorId: '' as number | '',
  keywordId: '' as number | '',
  status: '' as CommentUsageStatus | '',
  keyword: '',
  page: 1,
  pageSize: 50,
})

const importForm = reactive({
  doctorId: '' as number | '',
})

const importRules: FormRules = {
  doctorId: [{ required: true, message: '请选择医生', trigger: 'change' }],
}

const selectedDoctorName = computed(() => {
  if (!query.doctorId) {
    return '全部医生'
  }
  return doctors.value.find((doctor) => doctor.id === query.doctorId)?.name || '已选医生'
})

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
  doctors.value = await getDoctorOptionsApi()
  keywordOptions.value = await getDoctorKeywordOptionsApi(query.doctorId)
}

const loadComments = async () => {
  loading.value = true
  try {
    const response = await getCommentBankApi(query)
    comments.value = response.items
    total.value = response.total
    selectedRows.value = []
  } finally {
    loading.value = false
  }
}

const searchComments = () => {
  query.page = 1
  loadComments()
}

const resetQuery = async () => {
  query.doctorId = ''
  query.keywordId = ''
  query.status = ''
  query.keyword = ''
  query.page = 1
  keywordOptions.value = await getDoctorKeywordOptionsApi()
  loadComments()
}

const removeComment = async (item: CommentBankItem) => {
  await ElMessageBox.confirm('确认删除这条评论内容？删除后不会再被任务分配。', '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await deleteCommentBankItemApi(item.id)
  ElMessage.success('评论已删除')
  if (comments.value.length === 1 && query.page > 1) {
    query.page -= 1
  }
  loadComments()
}

const handleSelectionChange = (rows: CommentBankItem[]) => {
  selectedRows.value = rows
}

const batchRemoveComments = async () => {
  const ids = selectedRows.value.map((item) => item.id)
  if (!ids.length) {
    ElMessage.warning('请先选择要删除的评论')
    return
  }

  await ElMessageBox.confirm(
    `确认删除已选中的 ${ids.length} 条评论内容？删除后不会再被任务分配。`,
    '批量删除确认',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
  const response = await batchDeleteCommentBankItemsApi({ ids })
  ElMessage.success(`已删除 ${response.deleted} 条评论`)
  if (comments.value.length <= response.deleted && query.page > 1) {
    query.page -= 1
  }
  await loadComments()
}

const openImportEntry = () => {
  importForm.doctorId = query.doctorId || ''
  selectedFile.value = null
  importDialogVisible.value = true
  window.setTimeout(() => importFormRef.value?.clearValidate(), 0)
}

const downloadTemplate = () => {
  const rows = [
    ['搜索词', '评论内容'],
    ['', '明山主任真的太牛了，颅底肿瘤这种高难度手术，在您手里稳稳的，专业又靠谱！'],
    ['脑膜瘤', '刷到明山主任是福气，看脑膜瘤、听神经瘤就找您，技术顶尖，人还特别有耐心。'],
  ]
  import('xlsx').then((XLSX) => {
    const worksheet = XLSX.utils.aoa_to_sheet(rows)
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, '评论词库')
    XLSX.writeFile(workbook, '评论词库导入模板.xlsx')
  })
}

const beforeFileUpload = (file: File) => {
  const isExcel =
    file.name.endsWith('.xlsx') ||
    file.name.endsWith('.xls') ||
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    file.type === 'application/vnd.ms-excel'
  if (!isExcel) {
    ElMessage.warning('请上传 .xlsx 或 .xls 文件')
    return false
  }
  selectedFile.value = file
  return false
}

const removeSelectedFile = () => {
  selectedFile.value = null
}

const handleFileChange = (uploadFile: UploadFile) => {
  selectedFile.value = uploadFile.raw || null
}

const submitImport = async () => {
  const valid = await importFormRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  if (!selectedFile.value) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }

  importLoading.value = true
  try {
    const response = await importCommentBankExcelApi({
      doctorId: Number(importForm.doctorId),
      file: selectedFile.value,
    })
    ElMessage.success(`导入完成：成功 ${response.imported} 条，跳过 ${response.skipped} 条`)
    importDialogVisible.value = false
    query.doctorId = Number(importForm.doctorId)
    query.keywordId = ''
    query.status = ''
    query.page = 1
    keywordOptions.value = await getDoctorKeywordOptionsApi(query.doctorId)
    await loadComments()
  } finally {
    importLoading.value = false
  }
}

const handlePageChange = (page: number) => {
  query.page = page
  loadComments()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadComments()
}

watch(
  () => query.doctorId,
  async (doctorId) => {
    query.keywordId = ''
    keywordOptions.value = await getDoctorKeywordOptionsApi(doctorId)
  },
)

onMounted(async () => {
  await loadOptions()
  await loadComments()
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">评论词库</h1>
        <p class="page-subtitle">按医生维护评论内容，支持 Excel 导入，搜索词可为空。</p>
      </div>
      <div class="toolbar-actions">
        <el-button :icon="Download" @click="downloadTemplate">下载模板</el-button>
        <el-button :icon="Upload" type="primary" @click="openImportEntry">导入 Excel</el-button>
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
            style="width: 170px"
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
            style="width: 190px"
          >
            <el-option
              v-for="keyword in keywordOptions"
              :key="keyword.id"
              :label="keyword.keyword"
              :value="keyword.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="未使用" value="unused" />
            <el-option label="已使用" value="used" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="评论内容 / 医生 / 关键词"
            style="width: 240px"
            @keyup.enter="searchComments"
          />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchComments">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <div class="summary-strip">
        <span>{{ selectedDoctorName }}</span>
        <span>共 {{ total }} 条评论，已选 {{ selectedRows.length }} 条</span>
      </div>

      <div class="table-actions">
        <el-button
          :disabled="!selectedRows.length"
          :icon="Delete"
          type="danger"
          @click="batchRemoveComments"
        >
          批量删除
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="comments"
        border
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="医生" min-width="110" prop="doctorName" />
        <el-table-column label="评论内容" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="comment-content">{{ row.content }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'unused'" effect="plain" type="success">未使用</el-tag>
            <el-tag v-else effect="plain" type="info">已使用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="使用设备" min-width="130">
          <template #default="{ row }">{{ row.usedDeviceName || '-' }}</template>
        </el-table-column>
        <el-table-column label="发布账号" min-width="130">
          <template #default="{ row }">{{ row.usedAccount || '-' }}</template>
        </el-table-column>
        <el-table-column label="使用时间" width="130">
          <template #default="{ row }">{{ formatDateTime(row.usedAt) }}</template>
        </el-table-column>
        <el-table-column label="导入时间" width="130">
          <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="82">
          <template #default="{ row }">
            <el-button :icon="Delete" link type="danger" @click="removeComment(row)"
              >删除</el-button
            >
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

    <el-dialog v-model="importDialogVisible" title="导入评论词库" width="560px">
      <el-alert
        class="import-tip"
        :closable="false"
        show-icon
        title="Excel 第一行必须包含：评论内容。搜索词可以为空，也不要求匹配医生关键词。"
        type="info"
      />

      <el-form ref="importFormRef" :model="importForm" :rules="importRules" label-width="92px">
        <el-form-item label="医生" prop="doctorId">
          <el-select
            v-model="importForm.doctorId"
            filterable
            placeholder="请选择医生"
            style="width: 100%"
          >
            <el-option
              v-for="doctor in doctors"
              :key="doctor.id"
              :label="doctor.name"
              :value="doctor.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Excel 文件">
          <el-upload
            accept=".xlsx,.xls"
            action="#"
            :auto-upload="false"
            :before-upload="beforeFileUpload"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="removeSelectedFile"
          >
            <el-button :icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">仅支持 `.xlsx` / `.xls`，一行一条评论，搜索词可为空。</div>
            </template>
          </el-upload>
          <div v-if="selectedFile" class="selected-file">已选择：{{ selectedFile.name }}</div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button :loading="importLoading" type="primary" @click="submitImport"
          >开始导入</el-button
        >
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.toolbar-actions {
  display: flex;
  gap: 8px;
}

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

.comment-content {
  color: #111827;
}

.table-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.import-tip {
  margin-bottom: 16px;
}

.upload-tip {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}

.selected-file {
  width: 100%;
  margin-top: 8px;
  color: #374151;
  font-size: 13px;
}
</style>
