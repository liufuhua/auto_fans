export type DailyTaskStatus = 'pending' | 'running' | 'completed' | 'stopped' | 'exception'
export type DailyTaskDispatchStatus =
  | 'not_dispatched'
  | 'dispatching'
  | 'dispatched'
  | 'dispatch_failed'

export type DailyTaskConfigPayload = {
  doctorId: number
  keywordId: number
  count: number
  sortOrder?: number
}

export type DailyTaskCreatePayload = {
  taskDate: string
  configs: DailyTaskConfigPayload[]
}

export type DailyTaskItem = {
  id: number
  taskId: number
  sortOrder: number
  doctorId: number
  doctorName: string
  doctorProvince: string
  doctorProvinces?: string[]
  keywordId: number
  keyword: string
  remainingCommentCount: number
  targetCount: number
  dispatchedCount: number
  claimedCount: number
  successCount: number
  failedCount: number
  status: DailyTaskStatus
}

export type DailyTask = {
  id: number
  taskDate: string
  status: DailyTaskStatus
  dispatchStatus: DailyTaskDispatchStatus
  dispatchStartedAt?: string | null
  dispatchFinishedAt?: string | null
  dispatchError?: string | null
  totalCount: number
  successCount: number
  failedCount: number
  stoppedCount: number
  createdBy: string
  createdAt: string
  startedAt?: string
  finishedAt?: string
  items: DailyTaskItem[]
}

export type DailyTaskQuery = {
  taskDate?: string
  status?: DailyTaskStatus | ''
  page: number
  pageSize: number
}

export type DailyTaskListResponse = {
  items: DailyTask[]
  total: number
}

export type DailyTaskDispatchResult = {
  taskId: number
  dispatchStatus: DailyTaskDispatchStatus
  deviceCount: number
  poolItemCount: number
  warnings: string[]
}

export type DailyTaskDevicePoolStatus =
  | 'pending'
  | 'claimed'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped'

export type DailyTaskDevicePoolTask = {
  id: number
  doctorName: string
  doctorRealName: string
  keyword: string
  commentContent: string
  status: DailyTaskDevicePoolStatus
}

export type DailyTaskDeviceDetail = {
  deviceId: number
  deviceName: string
  deviceProvince: string
  assignedCount: number
  claimedCount: number
  successCount: number
  failedCount: number
  tasks: DailyTaskDevicePoolTask[]
}

export type DailyTaskDeviceDetailsResponse = {
  taskId: number
  items: DailyTaskDeviceDetail[]
}

export type DailyTaskItemSortOrderUpdate = {
  id: number
  sortOrder: number
}

export type DailyTaskItemSortOrderPayload = {
  items: DailyTaskItemSortOrderUpdate[]
}
