import { API_ENDPOINTS } from './endpoints'
import { request } from './request'
import type {
  DoctorProvinceItem,
  DoctorProvinceListResponse,
  DoctorProvincePayload,
  DoctorProvinceQuery,
} from '../types/doctorProvince'

export const getDoctorProvincesApi = async (
  query: DoctorProvinceQuery,
): Promise<DoctorProvinceListResponse> => {
  return request.get<DoctorProvinceListResponse, DoctorProvinceListResponse>(
    API_ENDPOINTS.doctorProvinces.list,
    {
      params: query,
    },
  )
}

export const getDoctorProvinceOptionsApi = async (): Promise<string[]> => {
  return request.get<string[], string[]>(API_ENDPOINTS.doctorProvinces.options)
}

export const updateDoctorProvincesApi = async (
  doctorId: number,
  payload: DoctorProvincePayload,
): Promise<DoctorProvinceItem> => {
  return request.put<DoctorProvinceItem, DoctorProvinceItem>(
    API_ENDPOINTS.doctorProvinces.update(doctorId),
    payload,
  )
}
