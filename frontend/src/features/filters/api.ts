import { apiClient } from '../../shared/api/client'

export interface FilterPreference {
  pt_ratio: number
}

export async function getFilterPreference() {
  const { data } = await apiClient.get<FilterPreference>('/users/me/filter-preference')
  return data
}

export async function saveFilterPreference(ptRatio: number) {
  const { data } = await apiClient.put<FilterPreference>('/users/me/filter-preference', {
    pt_ratio: ptRatio,
  })
  return data
}