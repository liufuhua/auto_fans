import type {
  DoctorItem,
  DoctorKeywordItem,
  DoctorKeywordPayload,
  DoctorListResponse,
  DoctorPayload,
  DoctorQuery,
  DoctorSortOrderPayload,
  RecordStatus,
} from '../types/doctor'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const DOCTOR_KEY = 'douyin_auto_mock_doctors'
const KEYWORD_KEY = 'douyin_auto_mock_doctor_keywords'

const now = () => new Date().toISOString()
const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const seedDoctors: DoctorItem[] = [
  {
    id: 1,
    name: '张明山',
    realName: '张明山',
    sortOrder: 1,
    remark: '颅底肿瘤、脑膜瘤、听神经瘤方向',
    status: 'active',
    remainingCommentCount: 2,
    keywordCommentCounts: [
      { keywordId: 1, keyword: '听神经瘤', remainingCommentCount: 1 },
      { keywordId: 2, keyword: '脑膜瘤', remainingCommentCount: 1 },
    ],
    createdAt: '2026-05-01T09:00:00.000Z',
    updatedAt: '2026-05-01T09:00:00.000Z',
  },
  {
    id: 2,
    name: '赵萌',
    realName: '赵萌',
    sortOrder: 2,
    remark: '神经调控相关测试医生',
    status: 'active',
    remainingCommentCount: 1,
    keywordCommentCounts: [
      { keywordId: 3, keyword: '偏瘫神经调控', remainingCommentCount: 1 },
    ],
    createdAt: '2026-05-02T09:00:00.000Z',
    updatedAt: '2026-05-02T09:00:00.000Z',
  },
]

const seedKeywords: DoctorKeywordItem[] = [
  {
    id: 1,
    doctorId: 1,
    keyword: '听神经瘤',
    remark: '',
    status: 'active',
    remainingCommentCount: 1,
    createdAt: '2026-05-01T09:20:00.000Z',
  },
  {
    id: 2,
    doctorId: 1,
    keyword: '脑膜瘤',
    remark: '',
    status: 'active',
    remainingCommentCount: 1,
    createdAt: '2026-05-01T09:22:00.000Z',
  },
  {
    id: 3,
    doctorId: 2,
    keyword: '偏瘫神经调控',
    remark: '',
    status: 'active',
    remainingCommentCount: 1,
    createdAt: '2026-05-02T10:00:00.000Z',
  },
]

const readJson = <T>(key: string, seed: T): T => {
  const raw = localStorage.getItem(key)
  if (!raw) {
    localStorage.setItem(key, JSON.stringify(seed))
    return seed
  }

  try {
    return JSON.parse(raw) as T
  } catch {
    localStorage.setItem(key, JSON.stringify(seed))
    return seed
  }
}

const writeJson = <T>(key: string, value: T) => {
  localStorage.setItem(key, JSON.stringify(value))
}

const readDoctors = () =>
  readJson<DoctorItem[]>(DOCTOR_KEY, seedDoctors).map((doctor, index) => ({
    ...doctor,
    sortOrder: doctor.sortOrder || index + 1,
  }))
const writeDoctors = (items: DoctorItem[]) => writeJson(DOCTOR_KEY, items)
const readKeywords = () => readJson<DoctorKeywordItem[]>(KEYWORD_KEY, seedKeywords)
const writeKeywords = (items: DoctorKeywordItem[]) => writeJson(KEYWORD_KEY, items)

const filterDoctors = (items: DoctorItem[], query: DoctorQuery) => {
  const keyword = query.keyword?.trim().toLowerCase()
  return items.filter((item) => {
    if (item.status === 'deleted') {
      return false
    }
    const matchesKeyword =
      !keyword ||
      item.name.toLowerCase().includes(keyword) ||
      item.realName.toLowerCase().includes(keyword) ||
      item.remark.toLowerCase().includes(keyword)
    const matchesStatus = !query.status || item.status === query.status
    return matchesKeyword && matchesStatus
  })
}

const getDoctorSortValue = (doctor: DoctorItem, sortBy: DoctorQuery['sortBy']) => {
  if (sortBy === 'realName') {
    return doctor.realName
  }
  if (sortBy === 'status') {
    return doctor.status
  }
  if (sortBy === 'createdAt') {
    return doctor.createdAt
  }
  if (sortBy === 'updatedAt') {
    return doctor.updatedAt
  }
  return doctor.name
}

export const getDoctorsApi = async (query: DoctorQuery): Promise<DoctorListResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    const filtered = filterDoctors(readDoctors(), query)
    if (query.sortBy && query.sortOrder) {
      const direction = query.sortOrder === 'descending' ? -1 : 1
      filtered.sort((a, b) => {
        const left = getDoctorSortValue(a, query.sortBy)
        const right = getDoctorSortValue(b, query.sortBy)
        return left.localeCompare(right, 'zh-CN') * direction || a.sortOrder - b.sortOrder || a.id - b.id
      })
    } else {
      filtered.sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id)
    }
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<DoctorListResponse, DoctorListResponse>(API_ENDPOINTS.doctors.list, {
    params: query,
  })
}

export const getDoctorOptionsApi = async (): Promise<DoctorItem[]> => {
  if (USE_MOCK_API) {
    await wait(100)
    return readDoctors()
      .filter((doctor) => doctor.status === 'active')
      .sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id)
  }

  return request.get<DoctorItem[], DoctorItem[]>(API_ENDPOINTS.doctors.options)
}

export const createDoctorApi = async (payload: DoctorPayload): Promise<DoctorItem> => {
  if (USE_MOCK_API) {
    await wait(160)
    const doctors = readDoctors()
    const nextDoctor: DoctorItem = {
      id: Math.max(0, ...doctors.map((doctor) => doctor.id)) + 1,
      name: payload.name,
      realName: payload.realName,
      sortOrder: Math.max(0, ...doctors.map((doctor) => doctor.sortOrder || 0)) + 1,
      remark: payload.remark,
      status: 'active',
      remainingCommentCount: 0,
      keywordCommentCounts: [],
      createdAt: now(),
      updatedAt: now(),
    }
    writeDoctors([nextDoctor, ...doctors])
    return nextDoctor
  }

  return request.post<DoctorItem, DoctorItem>(API_ENDPOINTS.doctors.create, payload)
}

export const updateDoctorApi = async (id: number, payload: DoctorPayload): Promise<DoctorItem> => {
  if (USE_MOCK_API) {
    await wait(160)
    const doctors = readDoctors()
    const nextDoctors = doctors.map((doctor) =>
      doctor.id === id ? { ...doctor, ...payload, updatedAt: now() } : doctor,
    )
    writeDoctors(nextDoctors)
    const updated = nextDoctors.find((doctor) => doctor.id === id)
    if (!updated) {
      throw new Error('医生不存在')
    }
    return updated
  }

  return request.put<DoctorItem, DoctorItem>(API_ENDPOINTS.doctors.update(id), payload)
}

export const updateDoctorSortOrderApi = async (
  payload: DoctorSortOrderPayload,
): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(160)
    const sortOrderById = new Map(payload.items.map((item) => [item.id, item.sortOrder]))
    writeDoctors(
      readDoctors().map((doctor) => ({
        ...doctor,
        sortOrder: sortOrderById.get(doctor.id) ?? doctor.sortOrder,
        updatedAt: sortOrderById.has(doctor.id) ? now() : doctor.updatedAt,
      })),
    )
    return
  }

  return request.put<void, void>(API_ENDPOINTS.doctors.sortOrder, payload)
}

export const updateDoctorStatusApi = async (id: number, status: RecordStatus): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(140)
    const doctors = readDoctors()
    writeDoctors(
      doctors.map((doctor) =>
        doctor.id === id ? { ...doctor, status, updatedAt: now() } : doctor,
      ),
    )
    return
  }

  const action = status === 'active' ? 'enable' : 'disable'
  return request.post<void, void>(
    action === 'enable' ? API_ENDPOINTS.doctors.enable(id) : API_ENDPOINTS.doctors.disable(id),
  )
}

export const deleteDoctorApi = async (id: number): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(140)
    writeDoctors(
      readDoctors().map((doctor) =>
        doctor.id === id ? { ...doctor, status: 'deleted', updatedAt: now() } : doctor,
      ),
    )
    return
  }

  return request.delete<void, void>(API_ENDPOINTS.doctors.delete(id))
}

export const getDoctorKeywordsApi = async (doctorId: number): Promise<DoctorKeywordItem[]> => {
  if (USE_MOCK_API) {
    await wait(120)
    return readKeywords().filter((item) => item.doctorId === doctorId && item.status !== 'deleted')
  }

  return request.get<DoctorKeywordItem[], DoctorKeywordItem[]>(
    API_ENDPOINTS.doctors.keywords(doctorId),
  )
}

export const getDoctorKeywordOptionsApi = async (
  doctorId?: number | '',
): Promise<DoctorKeywordItem[]> => {
  if (USE_MOCK_API) {
    await wait(100)
    const activeDoctorIds = new Set(
      readDoctors()
        .filter((doctor) => doctor.status === 'active')
        .map((doctor) => doctor.id),
    )
    return readKeywords().filter((item) => {
      const matchesDoctor = !doctorId || item.doctorId === doctorId
      return matchesDoctor && item.status === 'active' && activeDoctorIds.has(item.doctorId)
    })
  }

  return request.get<DoctorKeywordItem[], DoctorKeywordItem[]>(
    API_ENDPOINTS.doctorKeywords.options,
    {
      params: { doctorId },
    },
  )
}

export const createDoctorKeywordApi = async (
  doctorId: number,
  payload: DoctorKeywordPayload,
): Promise<DoctorKeywordItem> => {
  if (USE_MOCK_API) {
    await wait(140)
    const keywords = readKeywords()
    const nextKeyword: DoctorKeywordItem = {
      id: Math.max(0, ...keywords.map((item) => item.id)) + 1,
      doctorId,
      keyword: payload.keyword,
      remark: payload.remark,
      status: 'active',
      remainingCommentCount: 0,
      createdAt: now(),
    }
    writeKeywords([nextKeyword, ...keywords])
    return nextKeyword
  }

  return request.post<DoctorKeywordItem, DoctorKeywordItem>(
    API_ENDPOINTS.doctors.keywords(doctorId),
    payload,
  )
}

export const updateDoctorKeywordApi = async (
  id: number,
  payload: DoctorKeywordPayload,
): Promise<DoctorKeywordItem> => {
  if (USE_MOCK_API) {
    await wait(140)
    const keywords = readKeywords()
    const nextKeywords = keywords.map((item) => (item.id === id ? { ...item, ...payload } : item))
    writeKeywords(nextKeywords)
    const updated = nextKeywords.find((item) => item.id === id)
    if (!updated) {
      throw new Error('关键词不存在')
    }
    return updated
  }

  return request.put<DoctorKeywordItem, DoctorKeywordItem>(
    API_ENDPOINTS.doctorKeywords.update(id),
    payload,
  )
}

export const updateDoctorKeywordStatusApi = async (
  id: number,
  status: RecordStatus,
): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(120)
    writeKeywords(readKeywords().map((item) => (item.id === id ? { ...item, status } : item)))
    return
  }

  const action = status === 'active' ? 'enable' : 'disable'
  return request.post<void, void>(
    action === 'enable'
      ? API_ENDPOINTS.doctorKeywords.enable(id)
      : API_ENDPOINTS.doctorKeywords.disable(id),
  )
}

export const deleteDoctorKeywordApi = async (id: number): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(120)
    writeKeywords(readKeywords().map((item) => (item.id === id ? { ...item, status: 'deleted' } : item)))
    return
  }

  return request.delete<void, void>(API_ENDPOINTS.doctorKeywords.delete(id))
}
