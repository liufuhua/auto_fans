<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Edit, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getRegionOptionsApi,
  getRegionRelationsApi,
  resetRegionRelationsApi,
  updateRegionRelationApi,
} from '../api/regionRelations'
import type { RegionRelationItem } from '../types/regionRelation'

const loading = ref(false)
const saving = ref(false)
const resetLoading = ref(false)
const dialogVisible = ref(false)
const relations = ref<RegionRelationItem[]>([])
const regionOptions = ref<string[]>([])
const keyword = ref('')
const editingItem = ref<RegionRelationItem | null>(null)

const form = reactive({
  neighbors: [] as string[],
})

const filteredRelations = computed(() => {
  const value = keyword.value.trim()
  if (!value) {
    return relations.value
  }
  return relations.value.filter(
    (item) => item.region.includes(value) || item.neighbors.some((neighbor) => neighbor.includes(value)),
  )
})

const selectableRegions = computed(() =>
  regionOptions.value.filter((region) => region !== editingItem.value?.region),
)

const loadData = async () => {
  loading.value = true
  try {
    ;[relations.value, regionOptions.value] = await Promise.all([
      getRegionRelationsApi(),
      getRegionOptionsApi(),
    ])
  } finally {
    loading.value = false
  }
}

const openEdit = (item: RegionRelationItem) => {
  editingItem.value = item
  form.neighbors = [...item.neighbors]
  dialogVisible.value = true
}

const saveRelation = async () => {
  if (!editingItem.value) {
    return
  }
  saving.value = true
  try {
    await updateRegionRelationApi(editingItem.value.id, {
      neighbors: form.neighbors,
    })
    ElMessage.success('地区关联已保存')
    dialogVisible.value = false
    await loadData()
  } finally {
    saving.value = false
  }
}

const resetDefaults = async () => {
  await ElMessageBox.confirm('确认恢复默认地区关联？当前手动调整会被覆盖。', '恢复默认', {
    type: 'warning',
    confirmButtonText: '恢复默认',
    cancelButtonText: '取消',
  })
  resetLoading.value = true
  try {
    relations.value = await resetRegionRelationsApi()
    regionOptions.value = await getRegionOptionsApi()
    ElMessage.success('已恢复默认地区关联')
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
        <h1 class="page-title">地区关联</h1>
        <p class="page-subtitle">维护每个省级地区的周边地区，用于设备网络省份的区域容错。</p>
      </div>
      <el-button :icon="Refresh" :loading="resetLoading" @click="resetDefaults">恢复默认</el-button>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" inline>
        <el-form-item label="搜索">
          <el-input
            v-model="keyword"
            clearable
            placeholder="地区 / 周边地区"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="filteredRelations" border>
        <el-table-column label="地区" prop="region" width="130" />
        <el-table-column label="周边地区" min-width="420">
          <template #default="{ row }">
            <div class="neighbor-tags">
              <el-tag v-for="neighbor in row.neighbors" :key="neighbor" effect="plain">
                {{ neighbor }}
              </el-tag>
              <span v-if="!row.neighbors.length" class="empty-text">未配置</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column fixed="right" label="操作" width="100">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="`编辑地区关联：${editingItem?.region || ''}`" width="560px">
      <el-form label-width="86px">
        <el-form-item label="周边地区">
          <el-select
            v-model="form.neighbors"
            clearable
            filterable
            multiple
            placeholder="选择周边地区"
            style="width: 100%"
          >
            <el-option
              v-for="region in selectableRegions"
              :key="region"
              :label="region"
              :value="region"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="saving" type="primary" @click="saveRelation">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.filter-form {
  margin-bottom: 12px;
}

.neighbor-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.empty-text {
  color: #909399;
}
</style>
