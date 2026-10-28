import { apiClient } from '../../shared/api/client'

export interface AudioUrl {
  url: string
  expires_at: string
}

// Enquanto não há TTS, o áudio de cada história fica nesta chave do armazenamento.
// Para enviar um de exemplo: docker compose exec api python -m scripts.upload_sample_audio --story 1
export function audioKeyForStory(storyId: number) {
  return `stories/${storyId}/audio.wav`
}

// A tag <audio> não envia o token, então a API entrega uma URL assinada (ver README, "Streaming de áudio")
export async function getAudioUrl(key: string) {
  const { data } = await apiClient.get<AudioUrl>('/audio/url', { params: { key } })
  return data
}
