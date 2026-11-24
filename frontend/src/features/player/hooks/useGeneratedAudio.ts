import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getSegmentAudio, type SegmentAudioStatus } from '../api'
import { nextReadySegment, skipFailed, sortByPosition, startIndexFor } from '../playlist'
import { useFullAudio } from './useFullAudio'
import { useGenerationStatus } from './useGenerationStatus'

export { POLL_MS } from './useGenerationStatus'

/**
 * Gera o áudio da história com o filtro e organiza a reprodução frase a frase.
 *
 * 1. Pede a geração e acompanha o status até ficar pronto ou falhar (`useGenerationStatus`).
 * 2. Toca as frases em ordem de posição assim que cada uma fica pronta, sem esperar a história toda.
 * 3. Frases que falharam são puladas.
 *
 * `current` (frase atual) + o tempo do <audio> formam a posição de escuta, caso o progresso seja salvo.
 *
 * `startPosition` é a `position` da frase por onde começar (retomar de onde parou); sem ela, começa da primeira.
 * `hold` segura a reprodução (não busca nenhuma URL) enquanto o usuário escolhe continuar ou recomeçar: a
 * geração segue em andamento, só o áudio espera.
 *
 * Quando a geração termina, busca também o áudio único da história (`track`, todas as frases num arquivo só).
 * Enquanto ele não chega (`fullPending`) as URLs por frase não são buscadas, para não tocar duas vezes; se ele
 * não puder ser obtido, o player segue frase a frase.
 */
export function useGeneratedAudio(
  storyId: number,
  filterId: number | null,
  { startPosition = 0, hold = false }: { startPosition?: number; hold?: boolean } = {},
) {
  const enabled = filterId !== null && Number.isInteger(storyId) && storyId > 0
  const { status, error } = useGenerationStatus(storyId, filterId, enabled)
  // Índice (na lista ordenada) da frase que o usuário quer ouvir; as que falharam são puladas abaixo.
  // Nulo: ainda não escolheu nada, vale a frase inicial (`startPosition`)
  const [index, setIndex] = useState<number | null>(null)
  const [urls, setUrls] = useState<Record<number, string>>({})
  // Frases prontas cuja URL não pôde ser obtida: tratadas como falha
  const [broken, setBroken] = useState<ReadonlySet<number>>(new Set())
  const requested = useRef(new Set<number>())

  // A geração terminou (prontas ou falhas): já dá para juntar tudo num áudio só
  const generationDone = status !== null && status.total > 0 && status.state !== 'pending' && status.state !== 'generating'
  const fullAudio = useFullAudio(storyId, filterId, enabled && generationDone)
  // Já buscou a URL de alguma frase: o player está no modo por frase e a próxima precisa continuar vindo
  const [sentencesStarted, setSentencesStarted] = useState(false)
  // Com o áudio único a caminho (ou já aqui, antes de qualquer frase tocar), as frases não são buscadas
  const holdUrls = hold || fullAudio.pending || (fullAudio.track !== null && !sentencesStarted)

  const segments = useMemo(() => sortByPosition(status?.segments ?? []), [status])

  const isSkipped = useCallback(
    (s: SegmentAudioStatus) => s.status === 'failed' || broken.has(s.segment_id),
    [broken],
  )

  // Frase atual: a escolhida pelo usuário, ou a inicial (a da posição pedida), sem as que falharam
  const currentIndex = skipFailed(segments, index ?? startIndexFor(segments, startPosition), isSkipped)
  const current: SegmentAudioStatus | null = segments[currentIndex] ?? null

  // Próxima frase pronta depois da atual, para já buscar a URL dela (troca de frase sem pausa)
  const nextReady = nextReadySegment(segments, currentIndex, isSkipped)

  const currentReadyId = current?.status === 'ready' ? current.segment_id : null
  const nextReadyId = nextReady?.segment_id ?? null

  useEffect(() => {
    if (filterId === null || holdUrls) return
    for (const segmentId of [currentReadyId, nextReadyId]) {
      if (segmentId === null || requested.current.has(segmentId)) continue
      requested.current.add(segmentId)
      setSentencesStarted(true)
      getSegmentAudio(segmentId, filterId)
        .then((audio) => setUrls((prev) => ({ ...prev, [segmentId]: audio.url })))
        .catch(() => setBroken((prev) => new Set(prev).add(segmentId)))
    }
  }, [currentReadyId, nextReadyId, filterId, holdUrls])

  const src = current ? (urls[current.segment_id] ?? null) : null
  const finished = segments.length > 0 && current === null
  const generating = status?.state === 'pending' || status?.state === 'generating'
  const skippedCount = segments.filter(isSkipped).length

  // Ao terminar uma frase, segue para a próxima (se ainda não estiver pronta, o player espera)
  const next = useCallback(() => setIndex(currentIndex + 1), [currentIndex])
  const restart = useCallback(() => setIndex(0), [])
  // Pula para uma frase (ex.: coluna da faixa de densidade); se ela falhou, segue para a próxima que dá
  const goTo = useCallback(
    (segmentId: number) => {
      const target = segments.findIndex((s) => s.segment_id === segmentId)
      if (target >= 0) setIndex(target)
    },
    [segments],
  )

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
    goTo,
    // Áudio único da história (null enquanto não chega, ou se não puder ser obtido)
    track: fullAudio.track,
    fullPending: fullAudio.pending,
  }
}
