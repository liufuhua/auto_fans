export type CommentUsageStatus = 'unused' | 'used'

export type CommentBankItem = {
  id: number
  doctorId: number
  doctorName: string
  keywordId?: number | null
  keyword: string
  content: string
  status: CommentUsageStatus
  usedDeviceName?: string
  usedAccount?: string
  usedAt?: string
  createdAt: string
}

export type CommentBankQuery = {
  doctorId?: number | ''
  keywordId?: number | ''
  status?: CommentUsageStatus | ''
  keyword?: string
  page: number
  pageSize: number
}

export type CommentBankListResponse = {
  items: CommentBankItem[]
  total: number
}

export type CommentBankImportPayload = {
  doctorId: number
  file: File
}

export type CommentBankImportResponse = {
  imported: number
  skipped: number
}

export type CommentBankBatchDeletePayload = {
  ids: number[]
}

export type CommentBankBatchDeleteResponse = {
  deleted: number
}
