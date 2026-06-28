export type RegionRelationItem = {
  id: number
  region: string
  neighbors: string[]
  createdAt: string
  updatedAt: string
}

export type RegionRelationPayload = {
  neighbors: string[]
}
