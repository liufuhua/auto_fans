<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()

const form = reactive({
  account: '',
  password: '',
})

const rules: FormRules = {
  account: [{ required: true, message: '请输入手机号或用户名称', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const login = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  await authStore.login(form)
  ElMessage.success('登录成功')
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
  router.replace(redirect)
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="login-title">抖音测试管理后台</div>
      <p class="login-subtitle">后台用户登录</p>

      <el-form
        ref="formRef"
        class="login-form"
        :model="form"
        :rules="rules"
        label-position="top"
        @keyup.enter="login"
      >
        <el-form-item label="手机号 / 用户名称" prop="account">
          <el-input v-model="form.account" :prefix-icon="User" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            placeholder="请输入密码"
            show-password
            type="password"
          />
        </el-form-item>
        <el-button class="login-button" :loading="authStore.loading" type="primary" @click="login">
          登录
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background: #eef2f7;
}

.login-panel {
  width: 380px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 28px;
  box-shadow: 0 14px 35px rgba(15, 23, 42, 0.08);
}

.login-title {
  color: #111827;
  font-size: 22px;
  font-weight: 700;
}

.login-subtitle {
  margin: 6px 0 22px;
  color: #6b7280;
  font-size: 14px;
}

.login-form {
  display: flex;
  flex-direction: column;
}

.login-button {
  width: 100%;
  margin-top: 4px;
}
</style>
