import type { AdminUser, LoginPayload, LoginResponse } from '../types/auth'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH !== 'false'

const mockUser: AdminUser = {
  id: 1,
  phone: '13800000000',
  username: '管理员',
  isActive: true,
  lastLoginAt: new Date().toISOString(),
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export const loginApi = async (payload: LoginPayload): Promise<LoginResponse> => {
  if (USE_MOCK_AUTH) {
    await wait(300)
    return {
      token: `mock-token-${payload.account || 'admin'}`,
      user: mockUser,
    }
  }

  return request.post<LoginResponse, LoginResponse>(API_ENDPOINTS.auth.login, payload)
}

export const getCurrentUserApi = async (): Promise<AdminUser> => {
  if (USE_MOCK_AUTH) {
    await wait(120)
    return mockUser
  }

  return request.get<AdminUser, AdminUser>(API_ENDPOINTS.auth.me)
}

export const logoutApi = async (): Promise<void> => {
  if (USE_MOCK_AUTH) {
    await wait(120)
    return
  }

  return request.post<void, void>(API_ENDPOINTS.auth.logout)
}
