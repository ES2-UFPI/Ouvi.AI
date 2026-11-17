import { apiClient } from '../../shared/api/client'

// Mesmos valores do contrato do backend (backend/app/modules/audio/schemas.py)
export type GenerationState = 'pending' | 'generating' | 'ready' | 'failed'

export interface SegmentAudioStatus {
  segment_id: number
  position: number
  status: GenerationState
  duration_ms: number | null
  error: string | null
}

export interface AudioGenerationStatus {
  story_id: number
  filter_id: number
  state: GenerationState
  total: number
  ready: number
  failed: number
  segments: SegmentAudioStatus[]
}

export interface SegmentAudio {
  url: string
  expires_at: string
  segment_id: number
  duration_ms: number
  format: string
}

// Dispara a geração do áudio da história com o filtro (202 = em andamento, 200 = tudo pronto)
export async function requestStoryAudio(storyId: number, filterId: number) {
  const { data } = await apiClient.post<AudioGenerationStatus>(`/stories/${storyId}/audio`, {
    filter_id: filterId,
  })
  return data
}

// Progresso da geração: o player consulta por polling
export async function getStoryAudioStatus(storyId: number, filterId: number) {
  const { data } = await apiClient.get<AudioGenerationStatus>(`/stories/${storyId}/audio/status`, {
    params: { filter_id: filterId },
  })
  return data
}

// A tag <audio> não envia o token, então a API entrega uma URL assinada por frase (aceita Range)
export async function getSegmentAudio(segmentId: number, filterId: number) {
  const { data } = await apiClient.get<SegmentAudio>(`/audio/segments/${segmentId}`, {
    params: { filter_id: filterId },
  })
  return data
}

// Onde cada frase fica no áudio único da história, em milissegundos desde o começo
export interface TrackSegment {
  segment_id: number
  position: number
  start_ms: number
  duration_ms: number
}

export interface FullAudio {
  url: string
  expires_at: string
  duration_ms: number
  format: string
  segments: TrackSegment[]
  // Frases que falharam e ficaram de fora do áudio
  skipped: number[]
}

// Áudio único da história (todas as frases juntas), para tocar de uma vez e voltar a qualquer palavra.
// 409 = alguma frase ainda não terminou de ser gerada
export async function getFullAudio(storyId: number, filterId: number) {
  const { data } = await apiClient.get<FullAudio>(`/stories/${storyId}/audio/full`, {
    params: { filter_id: filterId },
  })
  return data
}
