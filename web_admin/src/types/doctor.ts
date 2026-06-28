export type RecordStatus = 'active' | 'disabled' | 'deleted'

export type DoctorItem = {
  id: number
  name: string
  realName: string
  sortOrder: number
  remark: string
  status: RecordStatus
  remainingCommentCount: number
  keywordCommentCounts: DoctorKeywordCommentCount[]
  createdAt: string
  updatedAt: string
}

export type DoctorKeywordCommentCount = {
  keywordId: number
  keyword: string
  remainingCommentCount: number
}

export type DoctorKeywordItem = {
  id: number
  doctorId: number
  keyword: string
  remark: string
  status: RecordStatus
  remainingCommentCount: number
  createdAt: string
}

export type DoctorQuery = {
  keyword?: string
  status?: RecordStatus | ''
  sortBy?: 'name' | 'realName' | 'status' | 'createdAt' | 'updatedAt' | ''
  sortOrder?: 'ascending' | 'descending' | ''
  page: number
  pageSize: number
}

export type DoctorListResponse = {
  items: DoctorItem[]
  total: number
}

export type DoctorPayload = {
  name: string
  realName: string
  remark: string
}

export type DoctorSortOrderUpdate = {
  id: number
  sortOrder: number
}

export type DoctorSortOrderPayload = {
  items: DoctorSortOrderUpdate[]
}

export type DoctorKeywordPayload = {
  keyword: string
  remark: string
}
