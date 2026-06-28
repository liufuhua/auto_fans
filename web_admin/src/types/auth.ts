export type AdminUser = {
  id: number
  phone: string
  username: string
  isActive: boolean
  lastLoginAt?: string
}

export type LoginPayload = {
  account: string
  password: string
}

export type LoginResponse = {
  token: string
  user: AdminUser
}
