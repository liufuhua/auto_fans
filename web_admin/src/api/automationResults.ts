import type {
  AutomationResultExportToDesktopResponse,
  AutomationResultItem,
  AutomationResultListResponse,
  AutomationResultQuery,
} from '../types/automationResult'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const RESULT_KEY = 'douyin_auto_mock_automation_results'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const seedResults: AutomationResultItem[] = [
  {
    id: 1,
    taskId: 1,
    taskDate: '2026-05-06',
    doctorId: 1,
    doctorName: '张明山',
    keywordId: 2,
    keyword: '脑膜瘤',
    deviceId: 1,
    deviceName: 'device_01',
    publishAccount: '测试账号01',
    commentContent: '刷到明山主任是福气，看脑膜瘤、听神经瘤就找您，技术顶尖，人还特别有耐心。',
    videoLink: 'https://example.com/video/10001',
    status: 'success',
    resultSummary:
      '任务：taskId=1, taskItemId=1\n医生：张明山\n关键词：脑膜瘤\n作者：张明山\n点赞：成功\n收藏：成功\n评论：成功\n页面等待：视频观看=80.20s\n后端回传：success\nresultId=1',
    startedAt: '2026-05-06T09:10:00.000Z',
    finishedAt: '2026-05-06T09:13:20.000Z',
  },
  {
    id: 2,
    taskId: 1,
    taskDate: '2026-05-06',
    doctorId: 1,
    doctorName: '张明山',
    keywordId: 1,
    keyword: '听神经瘤',
    deviceId: 2,
    deviceName: 'device_02',
    publishAccount: '测试账号02',
    commentContent: '业内公认的听瘤专家，保面、保听做得特别好，患者术后恢复快，太厉害了！',
    videoLink: '',
    status: 'failed',
    resultSummary:
      '任务：taskId=1, taskItemId=2\n医生：张明山\n关键词：听神经瘤\n作者：-\n点赞：未完成\n收藏：未完成\n评论：未完成\n后端回传：failed\nresultId=2',
    failReason: '评论按钮未找到，疑似页面结构变化',
    startedAt: '2026-05-06T09:12:00.000Z',
    finishedAt: '2026-05-06T09:15:45.000Z',
  },
]

const readResults = (): AutomationResultItem[] => {
  const raw = localStorage.getItem(RESULT_KEY)
  if (!raw) {
    localStorage.setItem(RESULT_KEY, JSON.stringify(seedResults))
    return seedResults
  }

  try {
    return JSON.parse(raw) as AutomationResultItem[]
  } catch {
    localStorage.setItem(RESULT_KEY, JSON.stringify(seedResults))
    return seedResults
  }
}

const filterResults = (items: AutomationResultItem[], query: AutomationResultQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return items.filter((item) => {
    const matchesTask = !query.taskId || item.taskId === query.taskId
    const matchesDoctor = !query.doctorId || item.doctorId === query.doctorId
    const matchesKeywordId = !query.keywordId || item.keywordId === query.keywordId
    const matchesDevice = !query.deviceId || item.deviceId === query.deviceId
    const matchesStatus = !query.status || item.status === query.status
    const matchesText =
      !keyword ||
      item.commentContent.toLowerCase().includes(keyword) ||
      item.publishAccount.toLowerCase().includes(keyword) ||
      item.resultSummary?.toLowerCase().includes(keyword) ||
      item.failReason?.toLowerCase().includes(keyword)

    return (
      matchesTask &&
      matchesDoctor &&
      matchesKeywordId &&
      matchesDevice &&
      matchesStatus &&
      matchesText
    )
  })
}

export const getAutomationResultsApi = async (
  query: AutomationResultQuery,
): Promise<AutomationResultListResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    const filtered = filterResults(readResults(), query)
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<AutomationResultListResponse, AutomationResultListResponse>(
    API_ENDPOINTS.automationResults.list,
    { params: query },
  )
}

export const exportAutomationResultsApi = async (
  startDate: string,
  endDate: string,
): Promise<Blob> => {
  if (USE_MOCK_API) {
    await wait(160)
    const normalizedStartDate = startDate <= endDate ? startDate : endDate
    const normalizedEndDate = startDate <= endDate ? endDate : startDate
    const rows = readResults().filter(
      (item) =>
        item.taskDate >= normalizedStartDate &&
        item.taskDate <= normalizedEndDate &&
        item.status === 'success',
    )
    const grouped = new Map<
      string,
      { taskDate: string; doctorName: string; keyword: string; count: number }
    >()
    for (const row of rows) {
      const key = `${row.taskDate}\u0000${row.doctorName}\u0000${row.keyword}`
      const current = grouped.get(key)
      if (current) {
        current.count += 1
      } else {
        grouped.set(key, {
          taskDate: row.taskDate,
          doctorName: row.doctorName,
          keyword: row.keyword,
          count: 1,
        })
      }
    }
    const XLSX = await import('xlsx')
    const worksheet = XLSX.utils.aoa_to_sheet([
      ['日期', '医生姓名', '关键词', '数量'],
      ...Array.from(grouped.values()).map((item) => [
        item.taskDate,
        item.doctorName,
        item.keyword,
        item.count,
      ]),
    ])
    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Sheet1')
    const buffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' })
    return new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
  }

  return request.get<Blob, Blob>(API_ENDPOINTS.automationResults.export, {
    params: { startDate, endDate },
    responseType: 'blob',
    timeout: 60000,
  })
}

export const exportAutomationResultsToDesktopApi = async (
  startDate: string,
  endDate: string,
): Promise<AutomationResultExportToDesktopResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    return {
      path: `桌面\\医生评论统计表_${startDate}_${endDate}.xlsx`,
    }
  }

  return request.post<
    AutomationResultExportToDesktopResponse,
    AutomationResultExportToDesktopResponse
  >(API_ENDPOINTS.automationResults.exportToDesktop, undefined, {
    params: { startDate, endDate },
    timeout: 60000,
  })
}
