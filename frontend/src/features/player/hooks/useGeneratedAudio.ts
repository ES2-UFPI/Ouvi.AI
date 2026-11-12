import axios from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getSegmentAudio,
  getStoryAudioStatus,
  requestStoryAudio,
  type AudioGenerationStatus,
  type SegmentAudioStatus,
} from '../api'

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
 * Gera o áudio da história com o filtro e organiza a reprodução frase a frase.
 *
 * 1. Pede a geração (POST) e acompanha o status por polling até ficar pronto ou falhar.
 * 2. Toca as frases em ordem de posição assim que cada uma fica pronta, sem esperar a história toda.
 * 3. Frases que falharam são puladas.
 *
 * `current` (frase atual) + o tempo do <audio> formam a posição de escuta, caso o progresso seja salvo.
 */
export function useGeneratedAudio(storyId: number, filterId: number | null) {
  const [status, setStatus] = useState<AudioGenerationStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Índice (na lista ordenada) da frase que o usuário quer ouvir; as que falharam são puladas abaixo
  const [index, setIndex] = useState(0)
  const [urls, setUrls] = useState<Record<number, string>>({})
  // Frases prontas cuja URL não pôde ser obtida: tratadas como falha
  const [broken, setBroken] = useState<ReadonlySet<number>>(new Set())
  const requested = useRef(new Set<number>())

  const enabled = filterId !== null && Number.isInteger(storyId) && storyId > 0

  // Dispara a geração e faz o polling do status até terminar (limpa o timer ao desmontar)
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

  const segments = useMemo(
    () => [...(status?.segments ?? [])].sort((a, b) => a.position - b.position),
    [status],
  )

  const isSkipped = useCallback(
    (s: SegmentAudioStatus) => s.status === 'failed' || broken.has(s.segment_id),
    [broken],
  )

  // Pula as frases que falharam a partir do índice pedido
  let currentIndex = index
  while (currentIndex < segments.length && isSkipped(segments[currentIndex])) currentIndex += 1
  const current: SegmentAudioStatus | null = segments[currentIndex] ?? null

  // Próxima frase pronta depois da atual, para já buscar a URL dela (troca de frase sem pausa)
  let nextReady: SegmentAudioStatus | null = null
  for (let i = currentIndex + 1; i < segments.length; i++) {
    if (isSkipped(segments[i])) continue
    if (segments[i].status === 'ready') nextReady = segments[i]
    break
  }

  const currentReadyId = current?.status === 'ready' ? current.segment_id : null
  const nextReadyId = nextReady?.segment_id ?? null

  useEffect(() => {
    if (filterId === null) return
    for (const segmentId of [currentReadyId, nextReadyId]) {
      if (segmentId === null || requested.current.has(segmentId)) continue
      requested.current.add(segmentId)
      getSegmentAudio(segmentId, filterId)
        .then((audio) => setUrls((prev) => ({ ...prev, [segmentId]: audio.url })))
        .catch(() => setBroken((prev) => new Set(prev).add(segmentId)))
    }
  }, [currentReadyId, nextReadyId, filterId])

  const src = current ? (urls[current.segment_id] ?? null) : null
  const finished = segments.length > 0 && current === null
  const generating = status?.state === 'pending' || status?.state === 'generating'
  const skippedCount = segments.filter(isSkipped).length

  // Ao terminar uma frase, segue para a próxima (se ainda não estiver pronta, o player espera)
  const next = useCallback(() => setIndex(currentIndex + 1), [currentIndex])
  const restart = useCallback(() => setIndex(0), [])

  return {
    status,
    error,
    segments,
    current,
    currentIndex,
    src,
    // A frase atual ainda está sendo gerada (ou a URL dela está a caminho)
    waiting: current !== null && src === null,
    generating,
    finished,
    skippedCount,
    next,
    restart,
  }
}
