export type AutomationResultStatus = 'success' | 'failed'
export type CommentRecheckStatus =
  | 'not_checked'
  | 'queued'
  | 'checking'
  | 'exists'
  | 'missing'
  | 'failed'
  | 'login_required'
  | 'captcha_required'

export type AutomationResultItem = {
  id: number
  taskId: number
  taskDate: string
  doctorId: number
  doctorName: string
  keywordId: number
  keyword: string
  deviceId: number
  deviceName: string
  publishAccount: string
  commentContent: string
  videoLink?: string
  status: AutomationResultStatus
  commentRecheckStatus?: CommentRecheckStatus
  commentRecheckFailReason?: string
  commentRecheckCheckedAt?: string
  resultSummary?: string
  failReason?: string
  startedAt: string
  finishedAt?: string
}

export type AutomationResultQuery = {
  taskId?: number | ''
  doctorId?: number | ''
  keywordId?: number | ''
  deviceId?: number | ''
  status?: AutomationResultStatus | ''
  keyword?: string
  page: number
  pageSize: number
}

export type AutomationResultListResponse = {
  items: AutomationResultItem[]
  total: number
}
