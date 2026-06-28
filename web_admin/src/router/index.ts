import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import AdminLayout from '../layouts/AdminLayout.vue'
import Login from '../views/Login.vue'
import Dashboard from '../views/Dashboard.vue'
import AdminUsers from '../views/AdminUsers.vue'
import Doctors from '../views/Doctors.vue'
import DoctorProvinces from '../views/DoctorProvinces.vue'
import CommentBank from '../views/CommentBank.vue'
import DailyTasks from '../views/DailyTasks.vue'
import Devices from '../views/Devices.vue'
import AutomationResults from '../views/AutomationResults.vue'
import AutomationTimingSettings from '../views/AutomationTimingSettings.vue'
import CommentRecheck from '../views/CommentRecheck.vue'
import ServiceStatus from '../views/ServiceStatus.vue'
import { useAuthStore } from '../stores/auth'

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: Login,
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: AdminLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: Dashboard,
        meta: { title: '控制台' },
      },
      {
        path: 'admin-users',
        name: 'admin-users',
        component: AdminUsers,
        meta: { title: '后台用户' },
      },
      {
        path: 'doctors',
        name: 'doctors',
        component: Doctors,
        meta: { title: '医生管理' },
      },
      {
        path: 'doctor-provinces',
        name: 'doctor-provinces',
        component: DoctorProvinces,
        meta: { title: '医生省份' },
      },
      {
        path: 'comment-bank',
        name: 'comment-bank',
        component: CommentBank,
        meta: { title: '评论词库' },
      },
      {
        path: 'daily-tasks',
        name: 'daily-tasks',
        component: DailyTasks,
        meta: { title: '每日任务' },
      },
      {
        path: 'devices',
        name: 'devices',
        component: Devices,
        meta: { title: '设备管理' },
      },
      {
        path: 'automation-results',
        name: 'automation-results',
        component: AutomationResults,
        meta: { title: '执行结果' },
      },
      {
        path: 'service-status',
        name: 'service-status',
        component: ServiceStatus,
        meta: { title: '服务状态' },
      },
      {
        path: 'automation-timing-settings',
        name: 'automation-timing-settings',
        component: AutomationTimingSettings,
        meta: { title: '配置管理' },
      },
      {
        path: 'comment-recheck',
        name: 'comment-recheck',
        component: CommentRecheck,
        meta: { title: '评论复检' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const isPublic = Boolean(to.meta.public)
  const hasSession = await authStore.ensureSession()

  if (!isPublic && !hasSession) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.path === '/login' && hasSession) {
    return '/dashboard'
  }

  return true
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${String(to.meta.title)} - 抖音自动化管理后台`
    : '抖音自动化管理后台'
})

export default router
