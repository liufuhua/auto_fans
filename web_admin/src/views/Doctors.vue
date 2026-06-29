<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import type { Sort } from 'element-plus'
import {
  CircleCheck,
  CircleClose,
  Delete,
  Edit,
  Plus,
  Refresh,
  Search,
} from '@element-plus/icons-vue'
import {
  createDoctorApi,
  createDoctorKeywordApi,
  deleteDoctorApi,
  deleteDoctorKeywordApi,
  getDoctorKeywordsApi,
  getDoctorsApi,
  updateDoctorApi,
  updateDoctorKeywordApi,
  updateDoctorKeywordStatusApi,
  updateDoctorSortOrderApi,
  updateDoctorStatusApi,
} from '../api/doctors'
import type {
  DoctorItem,
  DoctorKeywordItem,
  DoctorKeywordPayload,
  DoctorPayload,
  RecordStatus,
} from '../types/doctor'

const loading = ref(false)
const doctors = ref<DoctorItem[]>([])
const total = ref(0)
const dialogVisible = ref(false)
const keywordDrawerVisible = ref(false)
const keywordDialogVisible = ref(false)
const editingDoctor = ref<DoctorItem | null>(null)
const currentDoctor = ref<DoctorItem | null>(null)
const editingKeyword = ref<DoctorKeywordItem | null>(null)
const doctorFormRef = ref<FormInstance>()
const keywordFormRef = ref<FormInstance>()
const keywordLoading = ref(false)
const keywords = ref<DoctorKeywordItem[]>([])
const sortSaving = ref(false)
const sortDirty = ref(false)
const draggingDoctorId = ref<number | null>(null)
const dragClientY = ref<number | null>(null)
const autoScrollAnimationFrame = ref<number | null>(null)
const manualSortEditIds = ref<number[]>([])

const query = reactive({
  keyword: '',
  status: '' as RecordStatus | '',
  sortBy: '' as 'name' | 'realName' | 'status' | 'createdAt' | 'updatedAt' | '',
  sortOrder: '' as 'ascending' | 'descending' | '',
  page: 1,
  pageSize: 50,
})

const doctorForm = reactive<DoctorPayload>({
  name: '',
  realName: '',
  remark: '',
})

const keywordForm = reactive<DoctorKeywordPayload>({
  keyword: '',
  remark: '',
})

const doctorDialogTitle = computed(() => (editingDoctor.value ? '编辑医生' : '新增医生'))
const keywordDialogTitle = computed(() => (editingKeyword.value ? '编辑关键词' : '新增关键词'))

const doctorRules: FormRules = {
  name: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  realName: [{ max: 64, message: '医生姓名最多 64 字', trigger: 'blur' }],
  remark: [{ max: 200, message: '备注最多 200 字', trigger: 'blur' }],
}

const keywordRules: FormRules = {
  keyword: [{ required: true, message: '请输入关键词', trigger: 'blur' }],
  remark: [{ max: 200, message: '备注最多 200 字', trigger: 'blur' }],
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

const loadDoctors = async () => {
  loading.value = true
  try {
    const response = await getDoctorsApi(query)
    doctors.value = response.items
    total.value = response.total
    sortDirty.value = false
    manualSortEditIds.value = []
  } finally {
    loading.value = false
  }
}

const searchDoctors = () => {
  query.page = 1
  loadDoctors()
}

const resetQuery = () => {
  query.keyword = ''
  query.status = ''
  query.sortBy = ''
  query.sortOrder = ''
  query.page = 1
  loadDoctors()
}

const openCreateDialog = () => {
  editingDoctor.value = null
  doctorForm.name = ''
  doctorForm.realName = ''
  doctorForm.remark = ''
  dialogVisible.value = true
  window.setTimeout(() => doctorFormRef.value?.clearValidate(), 0)
}

const openEditDialog = (doctor: DoctorItem) => {
  editingDoctor.value = doctor
  doctorForm.name = doctor.name
  doctorForm.realName = doctor.realName || ''
  doctorForm.remark = doctor.remark
  dialogVisible.value = true
  window.setTimeout(() => doctorFormRef.value?.clearValidate(), 0)
}

const submitDoctor = async () => {
  const valid = await doctorFormRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  if (editingDoctor.value) {
    await updateDoctorApi(editingDoctor.value.id, doctorForm)
    ElMessage.success('医生已更新')
  } else {
    await createDoctorApi(doctorForm)
    ElMessage.success('医生已创建')
  }

  dialogVisible.value = false
  loadDoctors()
}

const toggleDoctorStatus = async (doctor: DoctorItem) => {
  const nextStatus: RecordStatus = doctor.status === 'active' ? 'disabled' : 'active'
  const actionText = nextStatus === 'active' ? '启用' : '禁用'
  await ElMessageBox.confirm(`确认${actionText}医生“${doctor.name}”？`, '操作确认', {
    confirmButtonText: actionText,
    cancelButtonText: '取消',
    type: 'warning',
  })
  await updateDoctorStatusApi(doctor.id, nextStatus)
  ElMessage.success(`医生已${actionText}`)
  loadDoctors()
}

const removeDoctor = async (doctor: DoctorItem) => {
  await ElMessageBox.confirm(
    `确认删除医生“${doctor.name}”？删除后该医生的关键词也会一并删除。`,
    '删除确认',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
  await deleteDoctorApi(doctor.id)
  ElMessage.success('医生已删除')
  loadDoctors()
}

const loadKeywords = async () => {
  if (!currentDoctor.value) {
    return
  }
  keywordLoading.value = true
  try {
    keywords.value = await getDoctorKeywordsApi(currentDoctor.value.id)
  } finally {
    keywordLoading.value = false
  }
}

const openCreateKeywordDialog = () => {
  editingKeyword.value = null
  keywordForm.keyword = ''
  keywordForm.remark = ''
  keywordDialogVisible.value = true
  window.setTimeout(() => keywordFormRef.value?.clearValidate(), 0)
}

const openEditKeywordDialog = (keyword: DoctorKeywordItem) => {
  editingKeyword.value = keyword
  keywordForm.keyword = keyword.keyword
  keywordForm.remark = keyword.remark
  keywordDialogVisible.value = true
  window.setTimeout(() => keywordFormRef.value?.clearValidate(), 0)
}

const submitKeyword = async () => {
  keywordForm.keyword = keywordForm.keyword.trim()
  keywordForm.remark = keywordForm.remark.trim()
  const valid = await keywordFormRef.value?.validate().catch(() => false)
  if (!valid || !currentDoctor.value) {
    return
  }

  if (editingKeyword.value) {
    await updateDoctorKeywordApi(editingKeyword.value.id, keywordForm)
    ElMessage.success('关键词已更新')
  } else {
    await createDoctorKeywordApi(currentDoctor.value.id, keywordForm)
    ElMessage.success('关键词已创建')
  }

  keywordDialogVisible.value = false
  loadKeywords()
}

const toggleKeywordStatus = async (keyword: DoctorKeywordItem) => {
  const nextStatus: RecordStatus = keyword.status === 'active' ? 'disabled' : 'active'
  const actionText = nextStatus === 'active' ? '启用' : '禁用'
  await updateDoctorKeywordStatusApi(keyword.id, nextStatus)
  ElMessage.success(`关键词已${actionText}`)
  loadKeywords()
}

const removeKeyword = async (keyword: DoctorKeywordItem) => {
  await ElMessageBox.confirm(`确认删除关键词“${keyword.keyword}”？`, '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  await deleteDoctorKeywordApi(keyword.id)
  ElMessage.success('关键词已删除')
  loadKeywords()
}

const handlePageChange = (page: number) => {
  query.page = page
  loadDoctors()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadDoctors()
}

const handleTableSortChange = ({ prop, order }: Sort) => {
  if (
    prop === 'name' ||
    prop === 'realName' ||
    prop === 'status' ||
    prop === 'createdAt' ||
    prop === 'updatedAt'
  ) {
    query.sortBy = order ? prop : ''
    query.sortOrder = order || ''
  } else {
    query.sortBy = ''
    query.sortOrder = ''
  }
  query.page = 1
  loadDoctors()
}

const markSortDirty = () => {
  sortDirty.value = true
}

const handleManualSortChange = (doctor: DoctorItem) => {
  markSortDirty()
  if (!manualSortEditIds.value.includes(doctor.id)) {
    manualSortEditIds.value.push(doctor.id)
  }
}

const currentPageSortBase = () => (query.page - 1) * query.pageSize

const normalizeCurrentPageSortOrders = () => {
  doctors.value.forEach((doctor, index) => {
    doctor.sortOrder = currentPageSortBase() + index + 1
  })
}

const handleSortDragStart = (doctor: DoctorItem, event: DragEvent) => {
  draggingDoctorId.value = doctor.id
  dragClientY.value = event.clientY
  event.dataTransfer?.setData('text/plain', String(doctor.id))
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
  startDragAutoScroll()
}

const handleSortDrop = (targetDoctor: DoctorItem) => {
  if (!draggingDoctorId.value || draggingDoctorId.value === targetDoctor.id) {
    draggingDoctorId.value = null
    stopDragAutoScroll()
    return
  }

  const fromIndex = doctors.value.findIndex((doctor) => doctor.id === draggingDoctorId.value)
  const toIndex = doctors.value.findIndex((doctor) => doctor.id === targetDoctor.id)
  if (fromIndex < 0 || toIndex < 0) {
    draggingDoctorId.value = null
    stopDragAutoScroll()
    return
  }

  const [movedDoctor] = doctors.value.splice(fromIndex, 1)
  doctors.value.splice(toIndex, 0, movedDoctor)
  normalizeCurrentPageSortOrders()
  sortDirty.value = true
  manualSortEditIds.value = []
  draggingDoctorId.value = null
  stopDragAutoScroll()
}

const handleSortDragEnd = () => {
  draggingDoctorId.value = null
  stopDragAutoScroll()
}

const handleDocumentDragOver = (event: DragEvent) => {
  dragClientY.value = event.clientY
}

const runDragAutoScroll = () => {
  const y = dragClientY.value
  if (y !== null && draggingDoctorId.value !== null) {
    const threshold = 96
    const maxStep = 22
    const bottomDistance = window.innerHeight - y
    let scrollStep = 0

    if (y < threshold) {
      scrollStep = -Math.ceil(((threshold - y) / threshold) * maxStep)
    } else if (bottomDistance < threshold) {
      scrollStep = Math.ceil(((threshold - bottomDistance) / threshold) * maxStep)
    }

    if (scrollStep !== 0) {
      const scrollElement = document.scrollingElement || document.documentElement
      scrollElement.scrollTop += scrollStep
    }
  }

  autoScrollAnimationFrame.value = window.requestAnimationFrame(runDragAutoScroll)
}

const startDragAutoScroll = () => {
  document.addEventListener('dragover', handleDocumentDragOver)
  if (autoScrollAnimationFrame.value === null) {
    autoScrollAnimationFrame.value = window.requestAnimationFrame(runDragAutoScroll)
  }
}

const stopDragAutoScroll = () => {
  document.removeEventListener('dragover', handleDocumentDragOver)
  dragClientY.value = null
  if (autoScrollAnimationFrame.value !== null) {
    window.cancelAnimationFrame(autoScrollAnimationFrame.value)
    autoScrollAnimationFrame.value = null
  }
}

const saveDoctorSortOrder = async () => {
  if (!doctors.value.length) {
    return
  }

  const manualSortItems = manualSortEditIds.value
    .map((doctorId) => doctors.value.find((doctor) => doctor.id === doctorId))
    .filter((doctor): doctor is DoctorItem => Boolean(doctor))
    .map((doctor) => ({
      id: doctor.id,
      sortOrder: Math.max(1, Math.round(Number(doctor.sortOrder || 1))),
    }))

  if (!manualSortItems.length) {
    normalizeCurrentPageSortOrders()
  }

  const sortItems = manualSortItems.length
    ? manualSortItems
    : doctors.value.map((doctor) => ({
        id: doctor.id,
        sortOrder: doctor.sortOrder,
      }))

  sortSaving.value = true
  try {
    await updateDoctorSortOrderApi({ items: sortItems })
    ElMessage.success('医生排序已保存')
    await loadDoctors()
  } finally {
    sortSaving.value = false
  }
}

onMounted(async () => {
  await loadDoctors()
})

onBeforeUnmount(() => {
  stopDragAutoScroll()
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">医生管理</h1>
        <p class="page-subtitle">维护医生昵称、医生姓名、关键词和备注。</p>
      </div>
      <div class="toolbar-actions">
        <el-button
          :icon="CircleCheck"
          :loading="sortSaving"
          :type="sortDirty ? 'primary' : 'default'"
          @click="saveDoctorSortOrder"
        >
          保存排序
        </el-button>
        <el-button :icon="Plus" type="primary" @click="openCreateDialog">新增医生</el-button>
      </div>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="昵称 / 医生姓名 / 备注"
            style="width: 220px"
            @keyup.enter="searchDoctors"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchDoctors">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="doctors" border @sort-change="handleTableSortChange">
        <el-table-column label="顺序ID" width="118">
          <template #default="{ row }">
            <div
              class="sort-cell"
              @dragover.prevent
              @drop.prevent="handleSortDrop(row)"
            >
              <button
                class="drag-handle"
                draggable="true"
                title="拖动排序"
                type="button"
                @dragend="handleSortDragEnd"
                @dragstart="handleSortDragStart(row, $event)"
              >
                ⋮⋮
              </button>
              <el-input-number
                v-model="row.sortOrder"
                class="sort-input"
                :controls="false"
                :min="1"
                size="small"
                @change="handleManualSortChange(row)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="昵称（搜索使用）" min-width="150" prop="name" sortable="custom" />
        <el-table-column label="医生姓名" min-width="120" prop="realName" sortable="custom">
          <template #default="{ row }">{{ row.realName || '-' }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="110" prop="remark" show-overflow-tooltip />
        <el-table-column label="剩余评论总数" width="130">
          <template #default="{ row }">
            <el-tag :type="row.remainingCommentCount > 0 ? 'success' : 'danger'" effect="plain">
              {{ row.remainingCommentCount }} 条
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" prop="status" sortable="custom">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'active'" effect="plain" type="success">启用</el-tag>
            <el-tag v-else effect="plain" type="danger">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170" prop="createdAt" sortable="custom">
          <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="170" prop="updatedAt" sortable="custom">
          <template #default="{ row }">{{ formatDateTime(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEditDialog(row)"
              >编辑</el-button
            >
            <el-button
              :icon="row.status === 'active' ? CircleClose : CircleCheck"
              link
              :type="row.status === 'active' ? 'danger' : 'success'"
              @click="toggleDoctorStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button :icon="Delete" link type="danger" @click="removeDoctor(row)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="doctorDialogTitle" width="480px">
      <el-form ref="doctorFormRef" :model="doctorForm" :rules="doctorRules" label-width="92px">
        <el-form-item label="昵称" prop="name">
          <el-input v-model="doctorForm.name" maxlength="64" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="医生姓名" prop="realName">
          <el-input v-model="doctorForm.realName" maxlength="64" placeholder="请输入医生姓名" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input
            v-model="doctorForm.remark"
            maxlength="200"
            placeholder="请输入备注"
            :rows="4"
            show-word-limit
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitDoctor">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="keywordDrawerVisible" size="720px" title="医生关键词">
      <template #header>
        <div>
          <strong>{{ currentDoctor?.name }} - 关键词管理</strong>
          <p class="drawer-subtitle">每日任务和评论词库会按关键词匹配。</p>
        </div>
      </template>

      <div class="keyword-toolbar">
        <el-button :icon="Plus" type="primary" @click="openCreateKeywordDialog">
          新增关键词
        </el-button>
      </div>

      <el-table v-loading="keywordLoading" :data="keywords" border>
        <el-table-column label="关键词" min-width="180" prop="keyword" />
        <el-table-column label="备注" min-width="220" prop="remark" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'active'" effect="plain" type="success">启用</el-tag>
            <el-tag v-else effect="plain" type="danger">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column fixed="right" label="操作" width="230">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEditKeywordDialog(row)">
              编辑
            </el-button>
            <el-button
              :icon="row.status === 'active' ? CircleClose : CircleCheck"
              link
              :type="row.status === 'active' ? 'danger' : 'success'"
              @click="toggleKeywordStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button :icon="Delete" link type="danger" @click="removeKeyword(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-dialog v-model="keywordDialogVisible" :title="keywordDialogTitle" width="460px">
      <el-form ref="keywordFormRef" :model="keywordForm" :rules="keywordRules" label-width="92px">
        <el-form-item label="关键词" prop="keyword">
          <el-input v-model="keywordForm.keyword" maxlength="50" placeholder="请输入关键词" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input
            v-model="keywordForm.remark"
            maxlength="200"
            placeholder="请输入备注"
            :rows="3"
            show-word-limit
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="keywordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitKeyword">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.filter-form {
  margin-bottom: 12px;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.drawer-subtitle {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.keyword-toolbar {
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
</style>
