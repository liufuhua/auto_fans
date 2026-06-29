export type CommentRecheckStatus =
  | 'not_checked'
  | 'queued'
  | 'checking'
  | 'exists'
  | 'missing'
  | 'failed'
  | 'login_required'
  | 'captcha_required'

export type CommentRecheckItem = {
  id: number
  automationResultId: number
  taskId: number
  taskDate: string
  doctorId: number
  doctorName: string
  keywordId?: number | null
  keyword: string
  deviceName: string
  publishAccount: string
  commentContent: string
  videoLink?: string
  status: CommentRecheckStatus
  checkedAt?: string
  failReason?: string
}

export type CommentRecheckQuery = {
  doctorId?: number | ''
  keywordId?: number | ''
  status?: CommentRecheckStatus | ''
  keyword?: string
  startDate?: string
  endDate?: string
  page: number
  pageSize: number
}

export type CommentRecheckListResponse = {
  items: CommentRecheckItem[]
  total: number
}

export type StartCommentRecheckPayload = {
  ids: number[]
}

export type StartCommentRecheckByDateRangePayload = {
  startDate: string
  endDate: string
}

export type StartCommentRecheckResponse = {
  submitted: number
  skipped: number
  loginRequired: boolean
}

export type CommentRecheckLoginStatus = {
  loggedIn: boolean
  sessionId?: string
  qrCodeUrl?: string
  message?: string
}

export type ConfirmCommentRecheckLoginPayload = {
  sessionId?: string
}
