import type { RegionRelationItem, RegionRelationPayload } from '../types/regionRelation'
import { API_ENDPOINTS } from './endpoints'
import { request } from './request'

export const getRegionRelationsApi = async (): Promise<RegionRelationItem[]> => {
  return request.get<RegionRelationItem[], RegionRelationItem[]>(API_ENDPOINTS.regionRelations.list)
}

export const getRegionOptionsApi = async (): Promise<string[]> => {
  return request.get<string[], string[]>(API_ENDPOINTS.regionRelations.options)
}

export const updateRegionRelationApi = async (
  id: number,
  payload: RegionRelationPayload,
): Promise<RegionRelationItem> => {
  return request.put<RegionRelationItem, RegionRelationItem>(
    API_ENDPOINTS.regionRelations.update(id),
    payload,
  )
}

export const resetRegionRelationsApi = async (): Promise<RegionRelationItem[]> => {
  return request.post<RegionRelationItem[], RegionRelationItem[]>(
    API_ENDPOINTS.regionRelations.resetDefaults,
  )
}
