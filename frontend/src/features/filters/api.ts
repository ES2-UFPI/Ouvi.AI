import { apiClient } from '../../shared/api/client'

// Mesmos valores do contrato do backend (backend/app/modules/filters/schemas.py)
export type BaseLanguage = 'pt' | 'en'
export type SegmentType = 'phrasal_verbs'
export type Density = 'low' | 'medium' | 'high'

export interface FilterRules {
  base_language: BaseLanguage
  segment_types: SegmentType[]
  density: Density
}

export interface FilterPayload {
  story_id: number | null
  rules: FilterRules
}

export interface ListeningFilter extends FilterPayload {
  id: number
  created_at: string
  updated_at: string
}

export async function listFilters() {
  const { data } = await apiClient.get<ListeningFilter[]>('/filters')
  return data
}

export async function getFilter(id: number) {
  const { data } = await apiClient.get<ListeningFilter>(`/filters/${id}`)
  return data
}

export async function createFilter(payload: FilterPayload) {
  const { data } = await apiClient.post<ListeningFilter>('/filters', payload)
  return data
}

export async function updateFilter(id: number, payload: FilterPayload) {
  const { data } = await apiClient.put<ListeningFilter>(`/filters/${id}`, payload)
  return data
}
