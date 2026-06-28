export type AdminUserStatus = 'active' | 'disabled'

export type AdminUserItem = {
  id: number
  phone: string
  username: string
  status: AdminUserStatus
  createdAt: string
  lastLoginAt?: string
}

export type AdminUserQuery = {
  keyword?: string
  status?: AdminUserStatus | ''
  page: number
  pageSize: number
}

export type AdminUserListResponse = {
  items: AdminUserItem[]
  total: number
}

export type AdminUserCreatePayload = {
  phone: string
  username: string
  password: string
}

export type AdminUserUpdatePayload = {
  phone: string
  username: string
}

export type ResetPasswordPayload = {
  password: string
}
