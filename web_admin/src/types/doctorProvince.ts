export type DoctorProvinceItem = {
  doctorId: number
  doctorName: string
  provinces: string[]
  updatedAt?: string
}

export type DoctorProvincePayload = {
  provinces: string[]
}

export type DoctorProvinceQuery = {
  keyword?: string
  page: number
  pageSize: number
}

export type DoctorProvinceListResponse = {
  items: DoctorProvinceItem[]
  total: number
}
