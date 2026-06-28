import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getCurrentUserApi, loginApi, logoutApi } from '../api/auth'
import { TOKEN_KEY, USER_KEY, clearAuthStorage } from '../api/request'
import type { AdminUser, LoginPayload } from '../types/auth'

const readStoredUser = (): AdminUser | null => {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) {
    return null
  }

  try {
    return JSON.parse(raw) as AdminUser
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<AdminUser | null>(readStoredUser())
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.username || '管理员')

  const persist = (nextToken: string, nextUser: AdminUser) => {
    token.value = nextToken
    user.value = nextUser
    localStorage.setItem(TOKEN_KEY, nextToken)
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  const clear = () => {
    token.value = ''
    user.value = null
    clearAuthStorage()
  }

  const login = async (payload: LoginPayload) => {
    loading.value = true
    try {
      const response = await loginApi(payload)
      if (!response.user.isActive) {
        clear()
        throw new Error('当前账号已被禁用')
      }
      persist(response.token, response.user)
    } finally {
      loading.value = false
    }
  }

  const fetchCurrentUser = async () => {
    if (!token.value) {
      return null
    }

    const nextUser = await getCurrentUserApi()
    if (!nextUser.isActive) {
      clear()
      throw new Error('当前账号已被禁用')
    }

    user.value = nextUser
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    return nextUser
  }

  const ensureSession = async () => {
    if (!token.value) {
      return false
    }

    if (user.value?.isActive) {
      return true
    }

    try {
      await fetchCurrentUser()
      return true
    } catch {
      clear()
      return false
    }
  }

  const logout = async () => {
    if (token.value) {
      await logoutApi().catch(() => undefined)
    }
    clear()
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    displayName,
    login,
    fetchCurrentUser,
    ensureSession,
    logout,
  }
})
