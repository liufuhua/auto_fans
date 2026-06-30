import { getDoctorKeywordOptionsApi, getDoctorOptionsApi } from './doctors'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'
import type {
  DailyTask,
  DailyTaskCreatePayload,
  DailyTaskDeviceDetailsResponse,
  DailyTaskDispatchResult,
  DailyTaskItem,
  DailyTaskItemSortOrderPayload,
  DailyTaskListResponse,
  DailyTaskQuery,
  DailyTaskStatus,
} from '../types/dailyTask'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false'
const DAILY_TASK_KEY = 'auto_fans_mock_daily_tasks'

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const now = () => new Date().toISOString()

const seedTasks: DailyTask[] = [
  {
    id: 1,
    taskDate: '2026-05-06',
    status: 'running',
    dispatchStatus: 'dispatched',
    dispatchStartedAt: '2026-05-06T09:03:00.000Z',
    dispatchFinishedAt: '2026-05-06T09:04:00.000Z',
    totalCount: 12,
    successCount: 5,
    failedCount: 1,
    stoppedCount: 0,
    createdBy: '管理员',
    createdAt: '2026-05-06T09:00:00.000Z',
    startedAt: '2026-05-06T09:05:00.000Z',
    items: [
      {
        id: 1,
        taskId: 1,
        sortOrder: 1,
        doctorId: 1,
        doctorName: '张明山',
        doctorProvince: '北京',
        doctorProvinces: ['北京'],
        keywordId: 1,
        keyword: '听神经瘤',
        remainingCommentCount: 0,
        targetCount: 4,
        dispatchedCount: 4,
        claimedCount: 4,
        successCount: 3,
        failedCount: 0,
        status: 'running',
      },
      {
        id: 2,
        taskId: 1,
        sortOrder: 2,
        doctorId: 1,
        doctorName: '张明山',
        doctorProvince: '北京',
        doctorProvinces: ['北京'],
        keywordId: 2,
        keyword: '脑膜瘤',
        remainingCommentCount: 0,
        targetCount: 5,
        dispatchedCount: 5,
        claimedCount: 3,
        successCount: 2,
        failedCount: 1,
        status: 'running',
      },
      {
        id: 3,
        taskId: 1,
        sortOrder: 3,
        doctorId: 2,
        doctorName: '赵萌',
        doctorProvince: '北京',
        doctorProvinces: ['北京'],
        keywordId: 3,
        keyword: '偏瘫神经调控',
        remainingCommentCount: 0,
        targetCount: 3,
        dispatchedCount: 3,
        claimedCount: 1,
        successCount: 0,
        failedCount: 0,
        status: 'pending',
      },
    ],
  },
]

const readTasks = (): DailyTask[] => {
  const raw = localStorage.getItem(DAILY_TASK_KEY)
  if (!raw) {
    localStorage.setItem(DAILY_TASK_KEY, JSON.stringify(seedTasks))
    return seedTasks
  }

  try {
    return JSON.parse(raw) as DailyTask[]
  } catch {
    localStorage.setItem(DAILY_TASK_KEY, JSON.stringify(seedTasks))
    return seedTasks
  }
}

const writeTasks = (tasks: DailyTask[]) => {
  localStorage.setItem(DAILY_TASK_KEY, JSON.stringify(tasks))
}

const filterTasks = (tasks: DailyTask[], query: DailyTaskQuery) =>
  tasks.filter((task) => {
    const matchesDate = !query.taskDate || task.taskDate === query.taskDate
    const matchesStatus = !query.status || task.status === query.status
    return matchesDate && matchesStatus
  })

const normalizeTask = (task: DailyTask): DailyTask => {
  const successCount = task.items.reduce((sum, item) => sum + item.successCount, 0)
  const failedCount = task.items.reduce((sum, item) => sum + item.failedCount, 0)
  const stoppedCount =
    task.status === 'stopped' ? Math.max(task.totalCount - successCount - failedCount, 0) : 0
  const finished = successCount + failedCount >= task.totalCount
  const status: DailyTaskStatus =
    task.status === 'stopped' ? 'stopped' : finished ? 'completed' : task.status

  return {
    ...task,
    items: task.items
      .map((item, index) => ({
        ...item,
        sortOrder: item.sortOrder || index + 1,
        dispatchedCount: item.dispatchedCount || 0,
      }))
      .sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id),
    dispatchStatus: task.dispatchStatus || 'not_dispatched',
    dispatchStartedAt: task.dispatchStartedAt || null,
    dispatchFinishedAt: task.dispatchFinishedAt || null,
    dispatchError: task.dispatchError || null,
    status,
    successCount,
    failedCount,
    stoppedCount,
    finishedAt: finished && !task.finishedAt ? now() : task.finishedAt,
  }
}

export const getDailyTasksApi = async (query: DailyTaskQuery): Promise<DailyTaskListResponse> => {
  if (USE_MOCK_API) {
    await wait(160)
    const tasks = readTasks().map(normalizeTask)
    writeTasks(tasks)
    const filtered = filterTasks(tasks, query)
    const start = (query.page - 1) * query.pageSize
    return {
      items: filtered.slice(start, start + query.pageSize),
      total: filtered.length,
    }
  }

  return request.get<DailyTaskListResponse, DailyTaskListResponse>(API_ENDPOINTS.dailyTasks.list, {
    params: query,
  })
}

export const getDailyTaskOptionsApi = async (): Promise<DailyTask[]> => {
  if (USE_MOCK_API) {
    await wait(100)
    return readTasks()
  }

  return request.get<DailyTask[], DailyTask[]>(API_ENDPOINTS.dailyTasks.options)
}

export const createDailyTaskApi = async (payload: DailyTaskCreatePayload): Promise<DailyTask> => {
  if (USE_MOCK_API) {
    await wait(220)
    const [doctors, keywords] = await Promise.all([
      getDoctorOptionsApi(),
      getDoctorKeywordOptionsApi(),
    ])
    const tasks = readTasks()
    const nextTaskId = Math.max(0, ...tasks.map((task) => task.id)) + 1
    const nextItemId =
      Math.max(0, ...tasks.flatMap((task) => task.items.map((item) => item.id))) + 1

    const items: DailyTaskItem[] = payload.configs.map((config, index) => {
      const doctor = doctors.find((item) => item.id === config.doctorId)
      const keyword = keywords.find((item) => item.id === config.keywordId)
      return {
        id: nextItemId + index,
        taskId: nextTaskId,
        sortOrder: config.sortOrder || index + 1,
        doctorId: config.doctorId,
        doctorName: doctor?.name || '未知医生',
        doctorProvince: '',
        doctorProvinces: [],
        keywordId: config.keywordId,
        keyword: keyword?.keyword || '未知关键词',
        remainingCommentCount: 0,
        targetCount: config.count,
        dispatchedCount: 0,
        claimedCount: 0,
        successCount: 0,
        failedCount: 0,
        status: 'pending',
      }
    })

    const nextTask: DailyTask = {
      id: nextTaskId,
      taskDate: payload.taskDate,
      status: 'pending',
      dispatchStatus: 'not_dispatched',
      dispatchStartedAt: null,
      dispatchFinishedAt: null,
      dispatchError: null,
      totalCount: items.reduce((sum, item) => sum + item.targetCount, 0),
      successCount: 0,
      failedCount: 0,
      stoppedCount: 0,
      createdBy: '管理员',
      createdAt: now(),
      items,
    }

    writeTasks([nextTask, ...tasks])
    return nextTask
  }

  return request.post<DailyTask, DailyTask>(API_ENDPOINTS.dailyTasks.create, payload)
}

export const updateDailyTaskItemSortOrderApi = async (
  id: number,
  payload: DailyTaskItemSortOrderPayload,
): Promise<DailyTask> => {
  if (USE_MOCK_API) {
    await wait(160)
    const tasks = readTasks()
    const nextTasks = tasks.map((task) => {
      if (task.id !== id || task.status !== 'pending') {
        return task
      }
      const sortOrderById = new Map(payload.items.map((item) => [item.id, item.sortOrder]))
      const nextItems = task.items
        .map((item) => ({
          ...item,
          sortOrder: sortOrderById.get(item.id) ?? item.sortOrder,
        }))
        .sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id)
        .map((item, index) => ({ ...item, sortOrder: index + 1 }))
      return { ...task, items: nextItems }
    })
    writeTasks(nextTasks)
    const updated = nextTasks.find((task) => task.id === id)
    if (!updated) {
      throw new Error('每日任务不存在')
    }
    return updated
  }

  return request.put<DailyTask, DailyTask>(API_ENDPOINTS.dailyTasks.sortItems(id), payload)
}

export const dispatchDailyTaskApi = async (id: number): Promise<DailyTaskDispatchResult> => {
  if (USE_MOCK_API) {
    await wait(180)
    const tasks = readTasks()
    const task = tasks.find((item) => item.id === id)
    if (!task) {
      throw new Error('每日任务不存在')
    }
    const dispatchStartedAt = now()
    const nextItems = task.items.map((item) => ({
      ...item,
      dispatchedCount: item.targetCount,
    }))
    const poolItemCount = nextItems.reduce((sum, item) => sum + (item.dispatchedCount || 0), 0)
    const deviceCount = Math.max(1, Math.min(nextItems.length, poolItemCount))
    const warnings =
      poolItemCount < task.totalCount ? ['部分任务明细目标条数为 0，已跳过分派。'] : []

    writeTasks(
      tasks.map((item) =>
        item.id === id
          ? {
              ...item,
              dispatchStatus: 'dispatched',
              dispatchStartedAt,
              dispatchFinishedAt: now(),
              dispatchError: null,
              items: nextItems,
            }
          : item,
      ),
    )

    return {
      taskId: id,
      dispatchStatus: 'dispatched',
      deviceCount,
      poolItemCount,
      warnings,
    }
  }

  return request.post<DailyTaskDispatchResult, DailyTaskDispatchResult>(
    API_ENDPOINTS.dailyTasks.dispatch(id),
  )
}

export const getDailyTaskDeviceDetailsApi = async (
  id: number,
): Promise<DailyTaskDeviceDetailsResponse> => {
  if (USE_MOCK_API) {
    await wait(140)
    const task = readTasks().map(normalizeTask).find((item) => item.id === id)
    if (!task) {
      throw new Error('每日任务不存在')
    }
    return {
      taskId: id,
      items: [
        {
          deviceId: 1,
          deviceName: '演示设备 1',
          deviceProvince: '北京',
          assignedCount: task.items.length,
          claimedCount: task.items.filter((item) => item.claimedCount > 0).length,
          successCount: task.items.filter((item) => item.successCount > 0).length,
          failedCount: task.items.filter((item) => item.failedCount > 0).length,
          tasks: task.items.map((item) => ({
            id: item.id,
            doctorName: item.doctorName,
            doctorRealName: '',
            keyword: item.keyword,
            commentContent: '演示评论内容',
            status:
              item.failedCount > 0
                ? 'failed'
                : item.successCount > 0
                  ? 'success'
                  : item.claimedCount > 0
                    ? 'claimed'
                    : 'pending',
          })),
        },
      ],
    }
  }

  return request.get<DailyTaskDeviceDetailsResponse, DailyTaskDeviceDetailsResponse>(
    API_ENDPOINTS.dailyTasks.deviceDetails(id),
  )
}

export const stopDailyTaskApi = async (id: number): Promise<void> => {
  if (USE_MOCK_API) {
    await wait(140)
    const tasks = readTasks()
    writeTasks(
      tasks.map((task) =>
        task.id === id
          ? {
              ...task,
              status: 'stopped',
              stoppedCount: Math.max(task.totalCount - task.successCount - task.failedCount, 0),
              finishedAt: now(),
              items: task.items.map((item) =>
                item.status === 'completed' ? item : { ...item, status: 'stopped' },
              ),
            }
          : task,
      ),
    )
    return
  }

  return request.post<void, void>(API_ENDPOINTS.dailyTasks.stop(id))
}
