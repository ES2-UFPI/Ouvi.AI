import { apiClient } from '../../shared/api/client'

export interface Story {
  id: number
  title: string
  description: string | null
}

export async function listStories() {
  const { data } = await apiClient.get<Story[]>('/stories')
  return data
}
