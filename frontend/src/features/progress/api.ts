import { apiClient } from '../../shared/api/client'
import { useAuthStore } from '../auth/store'

// Mesmos valores do contrato do backend (backend/app/modules/progress/schemas.py)
export interface Progress {
  story_id: number
  filter_id: number | null
  // Posição (`position`) da frase em que o usuário parou; o primeiro valor é 0
  segment_position: number
  offset_ms: number
  completed: boolean
  client_time: string
  updated_at: string
}

export interface ProgressPayload {
  segment_position: number
  offset_ms: number
  filter_id: number | null
  completed: boolean
}

// 204 = a história ainda não foi começada: sem progresso (devolve null, não é erro)
export async function getProgress(storyId: number) {
  const { data, status } = await apiClient.get<Progress | ''>(`/stories/${storyId}/progress`)
  return status === 204 || !data ? null : data
}

export async function saveProgress(storyId: number, payload: ProgressPayload) {
  const { data } = await apiClient.put<Progress>(`/stories/${storyId}/progress`, {
    ...payload,
    client_time: new Date().toISOString(),
  })
  return data
}

export async function deleteProgress(storyId: number) {
  await apiClient.delete(`/stories/${storyId}/progress`)
}

// Histórias em andamento, da mais recente para a mais antiga ("Continuar ouvindo")
export async function listRecentProgress(limit = 5) {
  const { data } = await apiClient.get<Progress[]>('/progress/recent', { params: { limit } })
  return data
}

/**
 * Salva ao fechar ou esconder a página. O axios (XHR) pode ser cancelado nessa hora; o `fetch` com
 * `keepalive` termina mesmo depois que a página sai. Falha em silêncio, como o resto do salvamento.
 */
export function saveProgressOnExit(storyId: number, payload: ProgressPayload) {
  const baseURL = apiClient.defaults.baseURL ?? ''
  const token = useAuthStore.getState().token
  if (!token) return
  try {
    void fetch(`${baseURL}/stories/${storyId}/progress`, {
      method: 'PUT',
      keepalive: true,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ ...payload, client_time: new Date().toISOString() }),
    }).catch(() => undefined)
  } catch {
    // sem rede ou sem fetch: o próximo salvamento cobre
  }
}
