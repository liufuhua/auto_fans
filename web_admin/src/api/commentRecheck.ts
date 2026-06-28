import type {
  CommentRecheckLoginStatus,
  CommentRecheckItem,
  CommentRecheckListResponse,
  CommentRecheckQuery,
  ConfirmCommentRecheckLoginPayload,
  StartCommentRecheckByDateRangePayload,
  StartCommentRecheckPayload,
  StartCommentRecheckResponse,
} from '../types/commentRecheck'
import { getAutomationResultsApi } from './automationResults'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const RECHECK_KEY = 'douyin_auto_mock_comment_recheck'
const PLAYWRIGHT_REQUEST_TIMEOUT = 120000

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const readRecords = (): CommentRecheckItem[] => {
  const raw = localStorage.getItem(RECHECK_KEY)
  if (!raw) {
    return []
  }

  try {
    return JSON.parse(raw) as CommentRecheckItem[]
  } catch {
    localStorage.removeItem(RECHECK_KEY)
    return []
  }
}

const writeRecords = (items: CommentRecheckItem[]) => {
  localStorage.setItem(RECHECK_KEY, JSON.stringify(items))
}

const ensureMockRecords = async () => {
  const current = readRecords()
  const resultResponse = await getAutomationResultsApi({
    status: 'success',
    page: 1,
    pageSize: 1000,
  })
  const existingResultIds = new Set(current.map((item) => item.automationResultId))
  const created = resultResponse.items
    .filter((item) => item.videoLink && !existingResultIds.has(item.id))
    .map<CommentRecheckItem>((item) => ({
      id: item.id,
      automationResultId: item.id,
      taskId: item.taskId,
      taskDate: item.taskDate,
      doctorId: item.doctorId,
      doctorName: item.doctorName,
      keywordId: item.keywordId,
      keyword: item.keyword,
      deviceName: item.deviceName,
      publishAccount: item.publishAccount,
      commentContent: item.commentContent,
      videoLink: item.videoLink,
      status: 'not_checked',
    }))

  if (created.length) {
    writeRecords([...created, ...current])
    return [...created, ...current]
  }
  return current
}

const filterRecords = (items: CommentRecheckItem[], query: CommentRecheckQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return items.filter((item) => {
    const matchesDoctor = !query.doctorId || item.doctorId === query.doctorId
    const matchesKeywordId = !query.keywordId || item.keywordId === query.keywordId
    const matchesStatus = !query.status || item.status === query.status
    const matchesStartDate = !query.startDate || item.taskDate >= query.startDate
    const matchesEndDate = !query.endDate || item.taskDate <= query.endDate
    const matchesText =
      !keyword ||
      item.commentContent.toLowerCase().includes(keyword) ||
      item.publishAccount.toLowerCase().includes(keyword) ||
      item.failReason?.toLowerCase().includes(keyword)
    return (
      matchesDoctor &&
      matchesKeywordId &&
      matchesStatus &&
      matchesStartDate &&
      matchesEndDate &&
      matchesText
    )
  })
}

export const getCommentRecheckApi = async (
  query: CommentRecheckQuery,
): Promise<CommentRecheckListResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    const filtered = filterRecords(await ensureMockRecords(), query)
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<CommentRecheckListResponse, CommentRecheckListResponse>(
    API_ENDPOINTS.commentRecheck.list,
    { params: query },
  )
}

export const startCommentRecheckApi = async (
  payload: StartCommentRecheckPayload,
): Promise<StartCommentRecheckResponse> => {
  if (USE_MOCK_API) {
    await wait(500)
    const now = new Date().toISOString()
    const idSet = new Set(payload.ids)
    const nextItems = (await ensureMockRecords()).map((item) => {
      if (!idSet.has(item.id)) {
        return item
      }

      const exists = item.id % 3 !== 0
      return {
        ...item,
        status: exists ? 'exists' : 'missing',
        checkedAt: now,
        failReason: exists ? '' : '浏览器解析后未找到对应评论内容',
      } satisfies CommentRecheckItem
    })
    writeRecords(nextItems)
    return {
      submitted: payload.ids.length,
      skipped: 0,
      loginRequired: false,
    }
  }

  return request.post<StartCommentRecheckResponse, StartCommentRecheckResponse>(
    API_ENDPOINTS.commentRecheck.start,
    payload,
    { timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
  )
}

export const startTodayCommentRecheckApi = async (): Promise<StartCommentRecheckResponse> => {
  if (USE_MOCK_API) {
    await wait(500)
    const today = new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date())
    const records = await ensureMockRecords()
    const nextItems = records.map((item) =>
      item.taskDate === today
        ? {
            ...item,
            status: 'queued' as const,
            checkedAt: undefined,
            failReason: '',
          }
        : item,
    )
    writeRecords(nextItems)
    return {
      submitted: nextItems.filter((item) => item.taskDate === today).length,
      skipped: 0,
      loginRequired: false,
    }
  }

  return request.post<StartCommentRecheckResponse, StartCommentRecheckResponse>(
    API_ENDPOINTS.commentRecheck.startToday,
    undefined,
    { timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
  )
}

export const startCommentRecheckByDateApi = async (
  taskDate: string,
): Promise<StartCommentRecheckResponse> => {
  if (USE_MOCK_API) {
    await wait(500)
    const records = await ensureMockRecords()
    const nextItems = records.map((item) =>
      item.taskDate === taskDate
        ? {
            ...item,
            status: 'queued' as const,
            checkedAt: undefined,
            failReason: '',
          }
        : item,
    )
    writeRecords(nextItems)
    return {
      submitted: nextItems.filter((item) => item.taskDate === taskDate).length,
      skipped: 0,
      loginRequired: false,
    }
  }

  return request.post<StartCommentRecheckResponse, StartCommentRecheckResponse>(
    API_ENDPOINTS.commentRecheck.startByDate,
    undefined,
    { params: { taskDate }, timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
  )
}

export const startCommentRecheckByDateRangeApi = async (
  payload: StartCommentRecheckByDateRangePayload,
): Promise<StartCommentRecheckResponse> => {
  if (USE_MOCK_API) {
    await wait(500)
    const startDate = payload.startDate <= payload.endDate ? payload.startDate : payload.endDate
    const endDate = payload.startDate <= payload.endDate ? payload.endDate : payload.startDate
    const records = await ensureMockRecords()
    let submitted = 0
    const nextItems = records.map((item) => {
      if (item.taskDate < startDate || item.taskDate > endDate) {
        return item
      }
      submitted += 1
      return {
        ...item,
        status: 'queued' as const,
        checkedAt: undefined,
        failReason: '',
      }
    })
    writeRecords(nextItems)
    return {
      submitted,
      skipped: 0,
      loginRequired: false,
    }
  }

  return request.post<StartCommentRecheckResponse, StartCommentRecheckResponse>(
    API_ENDPOINTS.commentRecheck.startByDateRange,
    undefined,
    {
      params: {
        startDate: payload.startDate,
        endDate: payload.endDate,
      },
      timeout: PLAYWRIGHT_REQUEST_TIMEOUT,
    },
  )
}

export const getCommentRecheckLoginStatusApi =
  async (): Promise<CommentRecheckLoginStatus> => {
    if (USE_MOCK_API) {
      await wait(120)
      return {
        loggedIn: false,
        message: 'Playwright 登录流程尚未接入',
      }
    }

    return request.get<CommentRecheckLoginStatus, CommentRecheckLoginStatus>(
      API_ENDPOINTS.commentRecheck.loginStatus,
      { timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
    )
  }

export const createCommentRecheckLoginSessionApi =
  async (): Promise<CommentRecheckLoginStatus> => {
    if (USE_MOCK_API) {
      await wait(120)
      return {
        loggedIn: false,
        message: 'Playwright 登录流程尚未接入',
      }
    }

    return request.post<CommentRecheckLoginStatus, CommentRecheckLoginStatus>(
      API_ENDPOINTS.commentRecheck.loginSession,
      undefined,
      { timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
    )
  }

export const getCommentRecheckLoginQrApi = async (sessionId: string): Promise<Blob> => {
  if (USE_MOCK_API) {
    await wait(120)
    return new Blob([], { type: 'image/png' })
  }

  return request.get<Blob, Blob>(API_ENDPOINTS.commentRecheck.loginQr, {
    params: { sessionId },
    responseType: 'blob',
    timeout: PLAYWRIGHT_REQUEST_TIMEOUT,
  })
}

export const confirmCommentRecheckLoginApi = async (
  payload: ConfirmCommentRecheckLoginPayload,
): Promise<CommentRecheckLoginStatus> => {
  if (USE_MOCK_API) {
    await wait(120)
    return {
      loggedIn: false,
      sessionId: payload.sessionId,
      message: '尚未启动 Playwright 登录会话',
    }
  }

  return request.post<CommentRecheckLoginStatus, CommentRecheckLoginStatus>(
    API_ENDPOINTS.commentRecheck.confirmLogin,
    payload,
    { timeout: PLAYWRIGHT_REQUEST_TIMEOUT },
  )
}
