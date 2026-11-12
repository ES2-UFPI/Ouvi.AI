import { apiClient } from '../../shared/api/client'

// Mesmos valores do contrato do backend (backend/app/modules/filters/schemas.py)
export type BaseLanguage = 'pt' | 'en'
// `advanced_vocabulary` (US11, Cenário C): as palavras raras faladas em inglês sobre a base português
export type SegmentType = 'phrasal_verbs' | 'difficult_words' | 'advanced_vocabulary'
export type Density = 'low' | 'medium' | 'high'
export type WordLevel = 'intermediate' | 'advanced'
// Progressão da densidade ao longo da história (US11): `fixed` nos Cenários A e B (padrão, ausente nas regras);
// `increasing` no Cenário C, em que a densidade escolhida é a densidade FINAL
export type Progression = 'fixed' | 'increasing'

export interface FilterRules {
  base_language: BaseLanguage
  segment_types: SegmentType[]
  density: Density
  // Só no Cenário B (base inglês); a API omite a chave quando não há nível
  word_level?: WordLevel
  // Só aparece quando é `increasing` (Cenário C): a API omite a fixa (o padrão)
  progression?: Progression
}

// Uma combinação aceita pela API: idioma base, tipos de trecho, níveis (vazio = sem nível) e progressão
export interface Scenario {
  base_language: BaseLanguage
  segment_types: SegmentType[]
  word_levels: WordLevel[]
  progressions: Progression[]
  description: string
}

export interface FilterOptions {
  scenarios: Scenario[]
  densities: Density[]
  word_levels: WordLevel[]
  progressions: Progression[]
}

// Combinações que a tela pode oferecer (tabela única do backend)
export async function getFilterOptions() {
  const { data } = await apiClient.get<FilterOptions>('/filters/options')
  return data
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
