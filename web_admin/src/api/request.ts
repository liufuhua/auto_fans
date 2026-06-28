import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'douyin_auto_admin_token'
const USER_KEY = 'douyin_auto_admin_user'

type ApiResponse<T = unknown> = {
  code: string
  message: string
  data: T
}

const clearAuthStorage = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

const pruneEmptyParams = (params: unknown) => {
  if (!params || typeof params !== 'object' || params instanceof FormData) {
    return params
  }

  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined),
  )
}

export const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
})

request.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  config.params = pruneEmptyParams(config.params)
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => {
    const payload = response.data as ApiResponse | unknown
    if (
      payload &&
      typeof payload === 'object' &&
      'code' in payload &&
      'message' in payload &&
      'data' in payload
    ) {
      const apiPayload = payload as ApiResponse
      if (apiPayload.code !== 'OK') {
        return Promise.reject(new Error(apiPayload.message || '请求失败'))
      }
      return apiPayload.data
    }
    return response.data
  },
  (error: AxiosError<{ message?: string }>) => {
    const status = error.response?.status
    const message = error.response?.data?.message || error.message || '请求失败'

    if (status === 401 || status === 403) {
      clearAuthStorage()
      ElMessage.error(status === 403 ? '当前账号已被禁用或无权访问' : '登录已失效，请重新登录')
      if (window.location.pathname !== '/login') {
        const redirect = encodeURIComponent(`${window.location.pathname}${window.location.search}`)
        window.location.href = `/login?redirect=${redirect}`
      }
    } else {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  },
)

export { TOKEN_KEY, USER_KEY, clearAuthStorage }
