<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { CircleCheck, CircleClose, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import {
  createDeviceApi,
  getDevicesApi,
  updateDeviceApi,
  updateDeviceEnabledStatusApi,
} from '../api/devices'
import { getDoctorProvinceOptionsApi } from '../api/doctorProvinces'
import type {
  DeviceEnabledStatus,
  DeviceItem,
  DeviceModel,
  DevicePayload,
  DeviceRuntimeStatus,
} from '../types/device'

const loading = ref(false)
const devices = ref<DeviceItem[]>([])
const total = ref(0)
const dialogVisible = ref(false)
const editingDevice = ref<DeviceItem | null>(null)
const formRef = ref<FormInstance>()
const regionOptions = ref<string[]>([])

const deviceModelOptions: Array<{ label: string; value: DeviceModel }> = [
  { label: 'vivo Y52', value: 'vivo_y52' },
  { label: '华为 nova SE6', value: 'huawei_nova_se6' },
]

const query = reactive({
  keyword: '',
  enabledStatus: '' as DeviceEnabledStatus | '',
  runtimeStatus: '' as DeviceRuntimeStatus | '',
  page: 1,
  pageSize: 50,
})

const form = reactive<DevicePayload>({
  name: '',
  udid: '',
  deviceModel: 'huawei_nova_se6',
  systemPort: 8201,
  appiumPort: 4723,
  province: '',
  remark: '',
})

const dialogTitle = computed(() => (editingDevice.value ? '编辑设备' : '新增设备'))

const runtimeText: Record<DeviceRuntimeStatus, string> = {
  offline: '离线',
  idle: '空闲',
  running: '执行任务中',
}

const runtimeTagType: Record<DeviceRuntimeStatus, 'info' | 'success' | 'primary'> = {
  offline: 'info',
  idle: 'success',
  running: 'primary',
}

const getRuntimeText = (status: DeviceRuntimeStatus) => runtimeText[status]
const getRuntimeTagType = (status: DeviceRuntimeStatus) => runtimeTagType[status]
const getDeviceModelText = (model?: DeviceModel) =>
  deviceModelOptions.find((item) => item.value === model)?.label || '-'

const appiumPortFromUrl = (value?: string | null) => {
  if (!value) {
    return null
  }
  const match = value.match(/:(\d+)(?:\/)?$/)
  return match ? Number(match[1]) : null
}

const getAppiumPortText = (device: DeviceItem) => appiumPortFromUrl(device.appiumServerUrl) ?? '-'

const rules: FormRules = {
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  udid: [{ required: true, message: '请输入 ADB UDID', trigger: 'blur' }],
  deviceModel: [{ required: true, message: '请选择设备型号', trigger: 'change' }],
  systemPort: [
    { required: true, message: '请输入 systemPort', trigger: 'blur' },
    {
      validator: (_rule, value: number, callback) => {
        if (!Number.isInteger(value) || value < 8200 || value > 8299) {
          callback(new Error('systemPort 建议使用 8200-8299 之间的整数'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  appiumPort: [
    { required: true, message: '请输入 appium port', trigger: 'blur' },
    {
      validator: (_rule, value: number, callback) => {
        if (!Number.isInteger(value) || value < 1 || value > 65535) {
          callback(new Error('appium port 必须是 1-65535 之间的整数'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
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

const loadDevices = async () => {
  loading.value = true
  try {
    const response = await getDevicesApi(query)
    devices.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const loadRegionOptions = async () => {
  regionOptions.value = await getDoctorProvinceOptionsApi()
}

const searchDevices = () => {
  query.page = 1
  loadDevices()
}

const resetQuery = () => {
  query.keyword = ''
  query.enabledStatus = ''
  query.runtimeStatus = ''
  query.page = 1
  loadDevices()
}

const openCreateDialog = () => {
  editingDevice.value = null
  form.name = ''
  form.udid = ''
  form.deviceModel = 'huawei_nova_se6'
  form.systemPort = 8201
  form.appiumPort = 4723
  form.province = ''
  form.remark = ''
  dialogVisible.value = true
  window.setTimeout(() => formRef.value?.clearValidate(), 0)
}

const openEditDialog = (device: DeviceItem) => {
  editingDevice.value = device
  form.name = device.name
  form.udid = device.udid
  form.deviceModel = device.deviceModel || 'huawei_nova_se6'
  form.systemPort = device.systemPort
  form.appiumPort = appiumPortFromUrl(device.appiumServerUrl) ?? 4723
  form.province = device.province || ''
  form.remark = device.remark
  dialogVisible.value = true
  window.setTimeout(() => formRef.value?.clearValidate(), 0)
}

const submitDevice = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  if (editingDevice.value) {
    await updateDeviceApi(editingDevice.value.id, form)
    ElMessage.success('设备已更新')
  } else {
    await createDeviceApi(form)
    ElMessage.success('设备已创建')
  }

  dialogVisible.value = false
  loadDevices()
}

const toggleEnabledStatus = async (device: DeviceItem) => {
  const nextStatus: DeviceEnabledStatus =
    device.enabledStatus === 'enabled' ? 'disabled' : 'enabled'
  const actionText = nextStatus === 'enabled' ? '启用' : '禁用'
  await ElMessageBox.confirm(`确认${actionText}设备“${device.name}”？`, '操作确认', {
    confirmButtonText: actionText,
    cancelButtonText: '取消',
    type: 'warning',
  })
  await updateDeviceEnabledStatusApi(device.id, nextStatus)
  ElMessage.success(`设备已${actionText}`)
  loadDevices()
}

const handlePageChange = (page: number) => {
  query.page = page
  loadDevices()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadDevices()
}

onMounted(async () => {
  await Promise.all([loadDevices(), loadRegionOptions()])
})
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">设备管理</h1>
        <p class="page-subtitle">维护 Android 设备的 UDID、systemPort、Appium 端口和在线状态。</p>
      </div>
      <el-button :icon="Plus" type="primary" @click="openCreateDialog">新增设备</el-button>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="设备名称 / UDID / 备注"
            style="width: 240px"
            @keyup.enter="searchDevices"
          />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-select
            v-model="query.enabledStatus"
            clearable
            placeholder="全部"
            style="width: 130px"
          >
            <el-option label="启用" value="enabled" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="运行状态">
          <el-select
            v-model="query.runtimeStatus"
            clearable
            placeholder="全部"
            style="width: 130px"
          >
            <el-option label="离线" value="offline" />
            <el-option label="空闲" value="idle" />
            <el-option label="执行任务中" value="running" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchDevices">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="devices" border>
        <el-table-column label="设备名称" min-width="120" prop="name" />
        <el-table-column label="ADB UDID" min-width="160" prop="udid" />
        <el-table-column label="设备型号" width="120">
          <template #default="{ row }">{{ getDeviceModelText(row.deviceModel) }}</template>
        </el-table-column>
        <el-table-column label="systemPort" width="120" prop="systemPort" />
        <el-table-column label="appium port" width="120">
          <template #default="{ row }">{{ getAppiumPortText(row) }}</template>
        </el-table-column>
        <el-table-column label="启用状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.enabledStatus === 'enabled'" effect="plain" type="success"
              >启用</el-tag
            >
            <el-tag v-else effect="plain" type="danger">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="运行状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getRuntimeTagType(row.runtimeStatus)" effect="plain">
              {{ getRuntimeText(row.runtimeStatus) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="省份" width="100">
          <template #default="{ row }">{{ row.province || '-' }}</template>
        </el-table-column>
        <el-table-column label="最后心跳" width="130">
          <template #default="{ row }">{{ formatDateTime(row.lastHeartbeatAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEditDialog(row)"
              >编辑</el-button
            >
            <el-button
              :icon="row.enabledStatus === 'enabled' ? CircleClose : CircleCheck"
              link
              :type="row.enabledStatus === 'enabled' ? 'danger' : 'success'"
              @click="toggleEnabledStatus(row)"
            >
              {{ row.enabledStatus === 'enabled' ? '禁用' : '启用' }}
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="108px">
        <el-form-item label="设备名称" prop="name">
          <el-input v-model="form.name" maxlength="40" placeholder="例如 device_01" />
        </el-form-item>
        <el-form-item label="ADB UDID" prop="udid">
          <el-input v-model="form.udid" maxlength="80" placeholder="例如 emulator-5554" />
        </el-form-item>
        <el-form-item label="设备型号" prop="deviceModel">
          <el-select v-model="form.deviceModel" placeholder="请选择设备型号" style="width: 100%">
            <el-option
              v-for="model in deviceModelOptions"
              :key="model.value"
              :label="model.label"
              :value="model.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="systemPort" prop="systemPort">
          <el-input-number
            v-model="form.systemPort"
            :max="8299"
            :min="8200"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="appium port" prop="appiumPort">
          <el-input-number
            v-model="form.appiumPort"
            :max="65535"
            :min="1"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="省份" prop="province">
          <el-select
            v-model="form.province"
            clearable
            filterable
            placeholder="选择省份"
            style="width: 100%"
          >
            <el-option
              v-for="region in regionOptions"
              :key="region"
              :label="region"
              :value="region"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input
            v-model="form.remark"
            maxlength="200"
            placeholder="请输入备注"
            :rows="3"
            show-word-limit
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitDevice">保存</el-button>
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

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

</style>
