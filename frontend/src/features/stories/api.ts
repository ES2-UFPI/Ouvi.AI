import { apiClient } from '../../shared/api/client'
import type { FilterRules } from '../filters/api'

export interface Story {
  id: number
  title: string
  description: string | null
  // Número de frases da história
  segment_count: number
}

export interface StoryAnnotation {
  id: number
  kind: string
  lemma: string
  en_start: number
  en_end: number
  en_text: string
  pt_start: number | null
  pt_end: number | null
  pt_text: string | null
  extra: Record<string, unknown>
}

export interface StorySegment {
  id: number
  position: number
  text_en: string
  text_pt: string
  annotations: StoryAnnotation[]
}

export interface StorySegments {
  story: { id: number; title: string; language: string }
  segments: StorySegment[]
}

export async function listStories() {
  const { data } = await apiClient.get<Story[]>('/stories')
  return data
}

export async function getStorySegments(storyId: number) {
  const { data } = await apiClient.get<StorySegments>(`/stories/${storyId}/segments`, {
    params: { aligned_only: true },
  })
  return data
}
// Prévia do texto com as trocas de idioma (GET /stories/{id}/preview): o mesmo cálculo que gera o áudio
export interface PreviewSwap {
  start: number
  end: number
  text: string
  spoken: string
  lang: string
  annotation_id: number
}

// Densidade de uma frase: `target` é a fração-alvo de trocas (0 a 1) naquela altura da história
export interface DensityPoint {
  segment_id: number
  position: number
  candidates: number
  swapped: number
  target: number
}

export interface StoryPreview {
  story: { id: number; title: string; language: string }
  rules: FilterRules
  totals: { segments: number; candidates: number; swapped: number }
  density_profile: DensityPoint[]
  segments: { id: number; position: number; text: string; swaps: PreviewSwap[] }[]
}

export async function getStoryPreview(storyId: number, filterId: number) {
  const { data } = await apiClient.get<StoryPreview>(`/stories/${storyId}/preview`, {
    params: { filter_id: filterId },
  })
  return data
}
