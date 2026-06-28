<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import {
  ChatDotRound,
  DataAnalysis,
  DocumentChecked,
  Files,
  House,
  Connection,
  Monitor,
  Location,
  Search,
  Setting,
  Timer,
  SwitchButton,
  User,
} from '@element-plus/icons-vue'

type MenuItem = {
  path: string
  title: string
  icon: unknown
}

type OpenTab = {
  path: string
  title: string
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const menuItems: MenuItem[] = [
  { path: '/dashboard', title: '控制台', icon: House },
  { path: '/admin-users', title: '后台用户', icon: User },
  { path: '/doctors', title: '医生管理', icon: Search },
  { path: '/doctor-provinces', title: '医生省份', icon: Location },
  { path: '/comment-bank', title: '评论词库', icon: ChatDotRound },
  { path: '/daily-tasks', title: '每日任务', icon: Files },
  { path: '/devices', title: '设备管理', icon: Monitor },
  { path: '/automation-results', title: '执行结果', icon: DocumentChecked },
  { path: '/service-status', title: '服务状态', icon: Connection },
  { path: '/automation-timing-settings', title: '配置管理', icon: Timer },
  { path: '/comment-recheck', title: '评论复检', icon: DataAnalysis },
]

const activePath = computed(() => route.path)
const openTabs = ref<OpenTab[]>([{ path: '/dashboard', title: menuItems[0].title }])
const pageTitle = computed(() => String(route.meta.title || '控制台'))

const resolveTabTitle = (path: string) =>
  String(route.path === path && route.meta.title ? route.meta.title : '') ||
  menuItems.find((item) => item.path === path)?.title ||
  path

const ensureRouteTab = () => {
  if (route.path === '/login') {
    return
  }

  const exists = openTabs.value.some((tab) => tab.path === route.path)
  if (!exists) {
    openTabs.value.push({
      path: route.path,
      title: resolveTabTitle(route.path),
    })
  }
}

watch(() => route.path, ensureRouteTab, { immediate: true })

const handleTabChange = (name: string | number) => {
  const path = String(name)
  if (path !== route.path) {
    router.push(path)
  }
}

const handleTabRemove = (name: string | number) => {
  const path = String(name)
  if (path === '/dashboard') {
    return
  }

  const index = openTabs.value.findIndex((tab) => tab.path === path)
  if (index === -1) {
    return
  }

  const nextTab = openTabs.value[index + 1] || openTabs.value[index - 1] || openTabs.value[0]
  openTabs.value = openTabs.value.filter((tab) => tab.path !== path)

  if (path === route.path) {
    router.push(nextTab?.path || '/dashboard')
  }
}

const logout = async () => {
  await authStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside class="admin-sidebar" width="232px">
      <div class="brand">
        <div class="brand-mark">抖</div>
        <div>
          <div class="brand-title">抖音测试后台</div>
          <div class="brand-subtitle">Automation Admin</div>
        </div>
      </div>

      <el-menu class="side-menu" :default-active="activePath" router>
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="admin-content">
      <el-header class="admin-header" height="58px">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>管理后台</el-breadcrumb-item>
            <el-breadcrumb-item>{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-actions">
          <el-tag effect="plain" type="success">本地环境</el-tag>
          <el-button :icon="Setting" text>设置</el-button>
          <el-dropdown>
            <button class="user-button" type="button">
              <span class="avatar">{{ authStore.displayName.slice(0, 1) }}</span>
              <span>{{ authStore.displayName }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :icon="SwitchButton" @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <div class="route-tabs">
        <el-tabs
          :model-value="activePath"
          type="card"
          @tab-change="handleTabChange"
          @tab-remove="handleTabRemove"
        >
          <el-tab-pane
            v-for="tab in openTabs"
            :key="tab.path"
            :closable="tab.path !== '/dashboard'"
            :label="tab.title"
            :name="tab.path"
          />
        </el-tabs>
      </div>

      <el-main class="admin-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
  background: #f5f7fb;
}

.admin-sidebar {
  flex: 0 0 232px;
  border-right: 1px solid #e5e7eb;
  background: #111827;
  color: #fff;
}

.admin-content {
  min-width: 0;
  max-width: calc(100vw - 232px);
  overflow-x: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 58px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-mark {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 6px;
  background: #10b981;
  color: #fff;
  font-size: 17px;
  font-weight: 700;
}

.brand-title {
  font-size: 15px;
  font-weight: 650;
  line-height: 1.2;
}

.brand-subtitle {
  margin-top: 2px;
  color: #9ca3af;
  font-size: 11px;
}

.side-menu {
  border-right: 0;
  background: transparent;
  padding: 10px 8px;
}

.side-menu :deep(.el-menu-item) {
  height: 42px;
  margin: 4px 0;
  border-radius: 6px;
  color: #d1d5db;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: #1f2937;
  color: #fff;
}

.side-menu :deep(.el-menu-item:hover) {
  background: #1f2937;
  color: #fff;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  padding: 0 20px;
}

.header-left {
  min-width: 0;
}

.header-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 10px;
}

.user-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  border: 0;
  background: transparent;
  color: #374151;
  cursor: pointer;
  font: inherit;
}

.avatar {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 50%;
  background: #e8f5ef;
  color: #047857;
  font-size: 13px;
  font-weight: 700;
}

.route-tabs {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  padding: 6px 18px 0;
}

.route-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: 0;
}

.route-tabs :deep(.el-tabs__nav) {
  border-radius: 6px 6px 0 0;
}

.route-tabs :deep(.el-tabs__item) {
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
}

.admin-main {
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
  padding: 18px;
}

@media (max-width: 1180px) {
  .admin-sidebar {
    flex-basis: 196px;
    width: 196px !important;
  }

  .admin-content {
    max-width: calc(100vw - 196px);
  }

  .brand {
    padding: 0 14px;
  }

  .brand-subtitle {
    display: none;
  }

  .side-menu {
    padding: 8px 6px;
  }

  .admin-header {
    padding: 0 14px;
  }

  .route-tabs {
    padding-right: 14px;
    padding-left: 14px;
  }

  .admin-main {
    padding: 14px;
  }
}
</style>
