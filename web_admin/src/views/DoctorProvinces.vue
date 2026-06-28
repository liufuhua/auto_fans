<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Edit, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getDoctorProvinceOptionsApi,
  getDoctorProvincesApi,
  updateDoctorProvincesApi,
} from '../api/doctorProvinces'
import type { DoctorProvinceItem } from '../types/doctorProvince'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const rows = ref<DoctorProvinceItem[]>([])
const total = ref(0)
const provinceOptions = ref<string[]>([])
const editingItem = ref<DoctorProvinceItem | null>(null)

const query = reactive({
  keyword: '',
  page: 1,
  pageSize: 50,
})

const form = reactive({
  provinces: [] as string[],
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

const loadRows = async () => {
  loading.value = true
  try {
    const response = await getDoctorProvincesApi(query)
    rows.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const loadOptions = async () => {
  provinceOptions.value = await getDoctorProvinceOptionsApi()
}

const searchRows = () => {
  query.page = 1
  loadRows()
}

const resetQuery = () => {
  query.keyword = ''
  query.page = 1
  loadRows()
}

const openEdit = (item: DoctorProvinceItem) => {
  editingItem.value = item
  form.provinces = [...item.provinces]
  dialogVisible.value = true
}

const saveProvinces = async () => {
  if (!editingItem.value) {
    return
  }
  saving.value = true
  try {
    await updateDoctorProvincesApi(editingItem.value.doctorId, {
      provinces: form.provinces,
    })
    ElMessage.success('医生省份已保存')
    dialogVisible.value = false
    await loadRows()
  } finally {
    saving.value = false
  }
}

const handlePageChange = (page: number) => {
  query.page = page
  loadRows()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadRows()
}

onMounted(async () => {
  await Promise.all([loadRows(), loadOptions()])
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">医生省份</h1>
        <p class="page-subtitle">配置每个医生允许哪些省份的设备领取任务。</p>
      </div>
      <el-button :icon="Refresh" @click="loadRows">刷新</el-button>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="搜索">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="医生姓名"
            style="width: 220px"
            @keyup.enter="searchRows"
          />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchRows">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border>
        <el-table-column label="医生姓名" min-width="160" prop="doctorName" />
        <el-table-column label="省份" min-width="420">
          <template #default="{ row }">
            <div class="province-tags">
              <el-tag v-for="province in row.provinces" :key="province" effect="plain">
                {{ province }}
              </el-tag>
              <span v-if="!row.provinces.length" class="empty-text">未配置</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column fixed="right" label="操作" width="110">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="`编辑医生省份：${editingItem?.doctorName || ''}`" width="560px">
      <el-form label-width="72px">
        <el-form-item label="省份">
          <el-select
            v-model="form.provinces"
            clearable
            filterable
            multiple
            placeholder="请选择省份"
            style="width: 100%"
          >
            <el-option
              v-for="province in provinceOptions"
              :key="province"
              :label="province"
              :value="province"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="saving" type="primary" @click="saveProvinces">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.filter-form {
  margin-bottom: 12px;
}

.province-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.empty-text {
  color: #909399;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
