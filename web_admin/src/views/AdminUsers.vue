<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { CircleCheck, CircleClose, Edit, Key, Plus, Refresh, Search } from '@element-plus/icons-vue'
import {
  createAdminUserApi,
  getAdminUsersApi,
  resetAdminUserPasswordApi,
  updateAdminUserApi,
  updateAdminUserStatusApi,
} from '../api/adminUsers'
import type {
  AdminUserCreatePayload,
  AdminUserItem,
  AdminUserStatus,
  AdminUserUpdatePayload,
} from '../types/adminUser'

const loading = ref(false)
const users = ref<AdminUserItem[]>([])
const total = ref(0)
const dialogVisible = ref(false)
const passwordDialogVisible = ref(false)
const editingUser = ref<AdminUserItem | null>(null)
const passwordTarget = ref<AdminUserItem | null>(null)
const formRef = ref<FormInstance>()
const passwordFormRef = ref<FormInstance>()

const query = reactive({
  keyword: '',
  status: '' as AdminUserStatus | '',
  page: 1,
  pageSize: 50,
})

const form = reactive<AdminUserCreatePayload>({
  phone: '',
  username: '',
  password: '',
})

const passwordForm = reactive({
  password: '',
})

const dialogTitle = computed(() => (editingUser.value ? '编辑用户' : '新增用户'))

const rules: FormRules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1\d{10}$/, message: '请输入 11 位手机号', trigger: 'blur' },
  ],
  username: [{ required: true, message: '请输入用户名称', trigger: 'blur' }],
  password: [
    {
      validator: (_rule, value: string, callback) => {
        if (!editingUser.value && !value) {
          callback(new Error('请输入密码'))
          return
        }
        if (value && value.length < 6) {
          callback(new Error('密码至少 6 位'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

const passwordRules: FormRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
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

const loadUsers = async () => {
  loading.value = true
  try {
    const response = await getAdminUsersApi(query)
    users.value = response.items
    total.value = response.total
  } finally {
    loading.value = false
  }
}

const searchUsers = () => {
  query.page = 1
  loadUsers()
}

const resetQuery = () => {
  query.keyword = ''
  query.status = ''
  query.page = 1
  loadUsers()
}

const openCreateDialog = () => {
  editingUser.value = null
  form.phone = ''
  form.username = ''
  form.password = ''
  dialogVisible.value = true
  window.setTimeout(() => formRef.value?.clearValidate(), 0)
}

const openEditDialog = (user: AdminUserItem) => {
  editingUser.value = user
  form.phone = user.phone
  form.username = user.username
  form.password = ''
  dialogVisible.value = true
  window.setTimeout(() => formRef.value?.clearValidate(), 0)
}

const submitUser = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  if (editingUser.value) {
    const payload: AdminUserUpdatePayload = {
      phone: form.phone,
      username: form.username,
    }
    await updateAdminUserApi(editingUser.value.id, payload)
    ElMessage.success('用户已更新')
  } else {
    await createAdminUserApi(form)
    ElMessage.success('用户已创建')
  }

  dialogVisible.value = false
  loadUsers()
}

const toggleStatus = async (user: AdminUserItem) => {
  const nextStatus: AdminUserStatus = user.status === 'active' ? 'disabled' : 'active'
  const actionText = nextStatus === 'active' ? '启用' : '禁用'
  await ElMessageBox.confirm(`确认${actionText}用户“${user.username}”？`, '操作确认', {
    confirmButtonText: actionText,
    cancelButtonText: '取消',
    type: 'warning',
  })
  await updateAdminUserStatusApi(user.id, nextStatus)
  ElMessage.success(`用户已${actionText}`)
  loadUsers()
}

const openPasswordDialog = (user: AdminUserItem) => {
  passwordTarget.value = user
  passwordForm.password = ''
  passwordDialogVisible.value = true
  window.setTimeout(() => passwordFormRef.value?.clearValidate(), 0)
}

const submitPassword = async () => {
  const valid = await passwordFormRef.value?.validate().catch(() => false)
  if (!valid || !passwordTarget.value) {
    return
  }

  await resetAdminUserPasswordApi(passwordTarget.value.id, {
    password: passwordForm.password,
  })
  ElMessage.success('密码已重置')
  passwordDialogVisible.value = false
}

const handlePageChange = (page: number) => {
  query.page = page
  loadUsers()
}

const handlePageSizeChange = (pageSize: number) => {
  query.pageSize = pageSize
  query.page = 1
  loadUsers()
}

onMounted(loadUsers)
</script>

<template>
  <section class="page-shell">
    <div class="page-toolbar">
      <div>
        <h1 class="page-title">后台用户</h1>
        <p class="page-subtitle">管理操作人员账号、禁用状态和密码重置。</p>
      </div>
      <el-button :icon="Plus" type="primary" @click="openCreateDialog">新增用户</el-button>
    </div>

    <div class="content-panel">
      <el-form class="filter-form" :model="query" inline>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="手机号 / 用户名称"
            style="width: 220px"
            @keyup.enter="searchUsers"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button :icon="Search" type="primary" @click="searchUsers">查询</el-button>
          <el-button :icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="users" border>
        <el-table-column label="手机号" min-width="140" prop="phone" />
        <el-table-column label="用户名称" min-width="140" prop="username" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'active'" effect="plain" type="success">启用</el-tag>
            <el-tag v-else effect="plain" type="danger">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="最后登录" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.lastLoginAt) }}</template>
        </el-table-column>
        <el-table-column fixed="right" label="操作" width="290">
          <template #default="{ row }">
            <el-button :icon="Edit" link type="primary" @click="openEditDialog(row)"
              >编辑</el-button
            >
            <el-button :icon="Key" link type="primary" @click="openPasswordDialog(row)">
              重置密码
            </el-button>
            <el-button
              :icon="row.status === 'active' ? CircleClose : CircleCheck"
              link
              :type="row.status === 'active' ? 'danger' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" maxlength="11" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="用户名称" prop="username">
          <el-input v-model="form.username" maxlength="30" placeholder="请输入用户名称" />
        </el-form-item>
        <el-form-item v-if="!editingUser" label="密码" prop="password">
          <el-input
            v-model="form.password"
            show-password
            type="password"
            placeholder="请输入密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordDialogVisible" title="重置密码" width="420px">
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="92px"
      >
        <el-form-item label="用户">
          <span>{{ passwordTarget?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="passwordForm.password"
            show-password
            type="password"
            placeholder="请输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitPassword">确认重置</el-button>
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
