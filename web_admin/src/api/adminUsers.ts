import type {
  AdminUserCreatePayload,
  AdminUserItem,
  AdminUserListResponse,
  AdminUserQuery,
  AdminUserStatus,
  AdminUserUpdatePayload,
  ResetPasswordPayload,
} from '../types/adminUser'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const MOCK_KEY = 'douyin_auto_mock_admin_users'

const now = () => new Date().toISOString()

const seedUsers: AdminUserItem[] = [
  {
    id: 1,
    phone: '13800000000',
    username: '管理员',
    status: 'active',
    createdAt: '2026-05-01T09:00:00.000Z',
    lastLoginAt: now(),
  },
  {
    id: 2,
    phone: '13900000000',
    username: '运营一号',
    status: 'active',
    createdAt: '2026-05-02T10:30:00.000Z',
  },
  {
    id: 3,
    phone: '13700000000',
    username: '测试观察员',
    status: 'disabled',
    createdAt: '2026-05-03T15:20:00.000Z',
  },
]

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const readMockUsers = (): AdminUserItem[] => {
  const raw = localStorage.getItem(MOCK_KEY)
  if (!raw) {
    localStorage.setItem(MOCK_KEY, JSON.stringify(seedUsers))
    return seedUsers
  }

  try {
    return JSON.parse(raw) as AdminUserItem[]
  } catch {
    localStorage.setItem(MOCK_KEY, JSON.stringify(seedUsers))
    return seedUsers
  }
}

const writeMockUsers = (users: AdminUserItem[]) => {
  localStorage.setItem(MOCK_KEY, JSON.stringify(users))
}

const filterUsers = (users: AdminUserItem[], query: AdminUserQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return users.filter((user) => {
    const matchesKeyword =
      !keyword ||
      user.phone.toLowerCase().includes(keyword) ||
      user.username.toLowerCase().includes(keyword)
    const matchesStatus = !query.status || user.status === query.status
    return matchesKeyword && matchesStatus
  })
}

export const getAdminUsersApi = async (query: AdminUserQuery): Promise<AdminUserListResponse> => {
  if (USE_MOCK_API) {
    await wait(180)
    const filtered = filterUsers(readMockUsers(), query)
    const start = (query.page - 1) * query.pageSize
    const end = start + query.pageSize
    return {
      items: filtered.slice(start, end),
      total: filtered.length,
    }
  }

  return request.get<AdminUserListResponse, AdminUserListResponse>(API_ENDPOINTS.adminUsers.list, {
    params: query,
  })
}

export const createAdminUserApi = async (
  payload: AdminUserCreatePayload,
): Promise<AdminUserItem> => {
  if (USE_MOCK_API) {
    await wait(180)
    const users = readMockUsers()
    const nextUser: AdminUserItem = {
      id: Math.max(0, ...users.map((user) => user.id)) + 1,
      phone: payload.phone,
      username: payload.username,
      status: 'active',
      createdAt: now(),
    }
    writeMockUsers([nextUser, ...users])
    return nextUser
  }

  return request.post<AdminUserItem, AdminUserItem>(API_ENDPOINTS.adminUsers.create, payload)
}

export const updateAdminUserApi = async (
  id: number,
  payload: AdminUserUpdatePayload,
): Promise<AdminUserItem> => {
  if (USE_MOCK_API) {
    await wait(180)
    const users = readMockUsers()
    const nextUsers = users.map((user) => (user.id === id ? { ...user, ...payload } : user))
    writeMockUsers(nextUsers)
    const updated = nextUsers.find((user) => user.id === id)
    if (!updated) {
      throw new Error('用户不存在')
    }
    return updated
  }

  return request.put<AdminUserItem, AdminUserItem>(API_ENDPOINTS.adminUsers.update(id), payload)
}

export const updateAdminUserStatusApi = async (
  id: number,
  status: AdminUserStatus,
): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(150)
    const users = readMockUsers()
    writeMockUsers(users.map((user) => (user.id === id ? { ...user, status } : user)))
    return
  }

  const action = status === 'active' ? 'enable' : 'disable'
  return request.post<void, void>(
    action === 'enable'
      ? API_ENDPOINTS.adminUsers.enable(id)
      : API_ENDPOINTS.adminUsers.disable(id),
  )
}

export const resetAdminUserPasswordApi = async (
  id: number,
  payload: ResetPasswordPayload,
): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(150)
    console.info(`Mock reset password for admin user ${id}`, payload.password)
    return
  }

  return request.post<void, void>(API_ENDPOINTS.adminUsers.resetPassword(id), payload)
}
