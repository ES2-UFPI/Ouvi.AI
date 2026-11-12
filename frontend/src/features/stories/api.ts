import { apiClient } from '../../shared/api/client'

export interface Story {
  id: number
  title: string
  description: string | null
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