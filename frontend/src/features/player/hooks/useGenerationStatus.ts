import axios from 'axios'
import { useEffect, useState } from 'react'
import { getStoryAudioStatus, requestStoryAudio, type AudioGenerationStatus } from '../api'

export const POLL_MS = 1500
// Falhas seguidas no polling antes de desistir (uma falha isolada de rede não derruba o player)
const MAX_POLL_ERRORS = 5

function requestError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (status === 404) return 'História ou filtro não encontrado.'
    if (status === 422) return 'Este filtro não pode ser usado com esta história.'
  }
  return 'Não foi possível gerar o áudio agora. Tente novamente em instantes.'
}

/**
 * Dispara a geração do áudio (POST) e acompanha o status por polling até ficar pronto ou falhar.
 *
 * Só se ocupa de pedir e acompanhar: o que fazer com cada frase (tocar, pular, buscar a URL) é do
 * `useGeneratedAudio`. O timer é limpo ao desmontar ou ao trocar de história ou filtro, e `enabled`
 * falso não pede nada.
 */
export function useGenerationStatus(storyId: number, filterId: number | null, enabled: boolean) {
  const [status, setStatus] = useState<AudioGenerationStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled || filterId === null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let pollErrors = 0

    const handle = (next: AudioGenerationStatus) => {
      if (cancelled) return
      pollErrors = 0
      setStatus(next)
      if (next.state === 'pending' || next.state === 'generating') {
        timer = setTimeout(poll, POLL_MS)
      }
    }
    const poll = () => {
      getStoryAudioStatus(storyId, filterId)
        .then(handle)
        .catch((err) => {
          if (cancelled) return
          pollErrors += 1
          if (pollErrors >= MAX_POLL_ERRORS) setError(requestError(err))
          else timer = setTimeout(poll, POLL_MS)
        })
    }

    requestStoryAudio(storyId, filterId)
      .then(handle)
      .catch((err) => {
        if (!cancelled) setError(requestError(err))
      })

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [enabled, storyId, filterId])

  return { status, error }
}
