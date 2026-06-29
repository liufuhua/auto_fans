import type {
  CommentBankBatchDeletePayload,
  CommentBankBatchDeleteResponse,
  CommentBankImportPayload,
  CommentBankImportResponse,
  CommentBankItem,
  CommentBankListResponse,
  CommentBankQuery,
} from '../types/commentBank'
import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from './doctors'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const COMMENT_BANK_KEY = 'douyin_auto_mock_comment_bank'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const seedComments: CommentBankItem[] = [
  {
    id: 1,
    doctorId: 1,
    doctorName: '张明山',
    keywordId: 2,
    keyword: '脑膜瘤',
    content: '明山主任真的太牛了，颅底肿瘤这种高难度手术，在您手里稳稳的，专业又靠谱！',
    status: 'unused',
    createdAt: '2026-05-04T09:00:00.000Z',
  },
  {
    id: 2,
    doctorId: 1,
    doctorName: '张明山',
    keywordId: 2,
    keyword: '脑膜瘤',
    content: '刷到明山主任是福气，看脑膜瘤、听神经瘤就找您，技术顶尖，人还特别有耐心。',
    status: 'used',
    usedDeviceName: 'device_01',
    usedAccount: '测试账号01',
    usedAt: '2026-05-05T10:15:00.000Z',
    createdAt: '2026-05-04T09:05:00.000Z',
  },
  {
    id: 3,
    doctorId: 1,
    doctorName: '张明山',
    keywordId: 1,
    keyword: '听神经瘤',
    content: '业内公认的听瘤专家，保面、保听做得特别好，患者术后恢复快，太厉害了！',
    status: 'unused',
    createdAt: '2026-05-04T09:08:00.000Z',
  },
  {
    id: 4,
    doctorId: 2,
    doctorName: '赵萌',
    keywordId: 3,
    keyword: '偏瘫神经调控',
    content: '赵医生在神经调控方向讲得很清楚，给患者和家属很多信心。',
    status: 'unused',
    createdAt: '2026-05-04T11:00:00.000Z',
  },
]

const readComments = (): CommentBankItem[] => {
  const raw = localStorage.getItem(COMMENT_BANK_KEY)
  if (!raw) {
    localStorage.setItem(COMMENT_BANK_KEY, JSON.stringify(seedComments))
    return seedComments
  }

  try {
    return JSON.parse(raw) as CommentBankItem[]
  } catch {
    localStorage.setItem(COMMENT_BANK_KEY, JSON.stringify(seedComments))
    return seedComments
  }
}

const writeComments = (items: CommentBankItem[]) => {
  localStorage.setItem(COMMENT_BANK_KEY, JSON.stringify(items))
}

const filterComments = (items: CommentBankItem[], query: CommentBankQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return items.filter((item) => {
    const matchesDoctor = !query.doctorId || item.doctorId === query.doctorId
    const matchesKeywordId = !query.keywordId || item.keywordId === query.keywordId
    const matchesStatus = !query.status || item.status === query.status
    const matchesText =
      !keyword ||
      item.content.toLowerCase().includes(keyword) ||
      item.keyword.toLowerCase().includes(keyword) ||
      item.doctorName.toLowerCase().includes(keyword)
    return matchesDoctor && matchesKeywordId && matchesStatus && matchesText
  })
}

const parseExcelRows = async (
  file: File,
): Promise<Array<{ searchWord: string; content: string }>> => {
  const XLSX = await import('xlsx')
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const firstSheetName = workbook.SheetNames[0]
  if (!firstSheetName) {
    return []
  }

  const worksheet = workbook.Sheets[firstSheetName]
  const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(worksheet, { defval: '' })
  return rows
    .map((row) => ({
      searchWord: String(row['搜索词'] || row['searchWord'] || row['keyword'] || '').trim(),
      content: String(row['评论内容'] || row['content'] || '').trim(),
    }))
    .filter((row) => row.content)
}

export const getCommentBankApi = async (
  query: CommentBankQuery,
): Promise<CommentBankListResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    const filtered = filterComments(readComments(), query)
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<CommentBankListResponse, CommentBankListResponse>(
    API_ENDPOINTS.commentBank.list,
    {
      params: query,
    },
  )
}

export const deleteCommentBankItemApi = async (id: number): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(120)
    writeComments(readComments().filter((item) => item.id !== id))
    return
  }

  return request.delete<void, void>(API_ENDPOINTS.commentBank.delete(id))
}

export const batchDeleteCommentBankItemsApi = async (
  payload: CommentBankBatchDeletePayload,
): Promise<CommentBankBatchDeleteResponse> => {
  if (USE_MOCK_API) {
    await wait(180)
    const idSet = new Set(payload.ids)
    const currentItems = readComments()
    writeComments(currentItems.filter((item) => !idSet.has(item.id)))
    return {
      deleted: currentItems.filter((item) => idSet.has(item.id)).length,
    }
  }

  return request.post<CommentBankBatchDeleteResponse, CommentBankBatchDeleteResponse>(
    API_ENDPOINTS.commentBank.batchDelete,
    payload,
  )
}

export const importCommentBankExcelApi = async (
  payload: CommentBankImportPayload,
): Promise<CommentBankImportResponse> => {
  if (USE_MOCK_API) {
    await wait(220)
    const [rows, doctors, keywords] = await Promise.all([
      parseExcelRows(payload.file),
      getDoctorOptionsApi(),
      getDoctorKeywordOptionsApi(payload.doctorId),
    ])
    const doctor = doctors.find((item) => item.id === payload.doctorId)
    if (!doctor) {
      throw new Error('请选择有效医生')
    }

    const currentItems = readComments()
    const nextIdStart = Math.max(0, ...currentItems.map((item) => item.id)) + 1
    const skipped = 0
    const importedItems: CommentBankItem[] = []

    rows.forEach((row, index) => {
      const matchedKeyword = keywords.find((item) => item.keyword === row.searchWord)

      importedItems.push({
        id: nextIdStart + importedItems.length + index,
        doctorId: doctor.id,
        doctorName: doctor.name,
        keywordId: matchedKeyword?.id ?? null,
        keyword: matchedKeyword?.keyword || row.searchWord,
        content: row.content,
        status: 'unused',
        createdAt: new Date().toISOString(),
      })
    })

    writeComments([...importedItems, ...currentItems])
    return {
      imported: importedItems.length,
      skipped,
    }
  }

  const formData = new FormData()
  formData.append('doctorId', String(payload.doctorId))
  formData.append('file', payload.file)

  return request.post<CommentBankImportResponse, CommentBankImportResponse>(
    API_ENDPOINTS.commentBank.importExcel,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
}
