import { useCallback, useEffect, useRef } from 'react'
import { saveProgress, saveProgressOnExit, type ProgressPayload } from './api'

// Intervalo entre os salvamentos enquanto o áudio toca
export const SAVE_INTERVAL_MS = 5000

export interface ListenPosition {
  // `position` da frase (o primeiro valor é 0) e o ponto dentro dela, em milissegundos
  segmentPosition: number
  offsetMs: number
}

interface Options {
  storyId: number
  filterId: number | null
  // Falso enquanto o usuário ainda não escolheu continuar ou recomeçar: salvar antes apagaria o progresso antigo
  enabled: boolean
  playing: boolean
  // Lê a posição atual na hora do salvamento (nulo = ainda não há o que salvar)
  getPosition: () => ListenPosition | null
}

type Pending = { completed: boolean; position?: ListenPosition }

/**
 * Guarda onde o usuário está na história, sem que ele perceba:
 * - a cada 5 s enquanto toca, ao pausar e ao fechar ou esconder a página;
 * - não repete uma posição que já foi salva;
 * - nunca há duas requisições ao mesmo tempo (o salvamento pedido durante outro espera a sua vez);
 * - falha de rede é ignorada: a posição vai no ciclo seguinte e o áudio nunca é interrompido.
 */
export function useProgressSaver({ storyId, filterId, enabled, playing, getPosition }: Options) {
  const getPositionRef = useRef(getPosition)
  useEffect(() => {
    getPositionRef.current = getPosition
  })

  const lastSaved = useRef<string | null>(null)
  const inFlight = useRef(false)
  const queued = useRef<Pending | null>(null)
  // O salvamento que esperava a vez chama de novo a versão mais recente de `save`
  const saveRef = useRef<(pending: Pending) => void>(() => undefined)

  const payloadOf = useCallback(
    (pending: Pending): ProgressPayload | null => {
      const position = pending.position ?? getPositionRef.current()
      if (!position) return null
      return {
        segment_position: position.segmentPosition,
        offset_ms: Math.max(0, Math.round(position.offsetMs)),
        filter_id: filterId,
        completed: pending.completed,
      }
    },
    [filterId],
  )

  const save = useCallback(
    (pending: Pending = { completed: false }) => {
      if (!enabled) return
      if (inFlight.current) {
        // Uma requisição está a caminho: guarda só o pedido mais recente e o faz quando ela acabar
        queued.current = pending
        return
      }
      const payload = payloadOf(pending)
      if (!payload) return
      const key = `${payload.segment_position}:${payload.offset_ms}:${payload.completed}`
      if (key === lastSaved.current) return

      inFlight.current = true
      saveProgress(storyId, payload)
        .then(() => {
          lastSaved.current = key
        })
        .catch(() => undefined)
        .finally(() => {
          inFlight.current = false
          const next = queued.current
          queued.current = null
          if (next) saveRef.current(next)
        })
    },
    [enabled, payloadOf, storyId],
  )
  useEffect(() => {
    saveRef.current = save
  }, [save])

  // A cada 5 s, só enquanto toca
  useEffect(() => {
    if (!enabled || !playing) return
    const timer = setInterval(() => save(), SAVE_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [enabled, playing, save])

  // Ao pausar, salva na hora (a transição de tocando para parado)
  const wasPlaying = useRef(false)
  useEffect(() => {
    if (wasPlaying.current && !playing) save()
    wasPlaying.current = playing
  }, [playing, save])

  // Ao fechar ou esconder a página (trocar de aba): o fetch com keepalive termina mesmo com a página saindo
  useEffect(() => {
    if (!enabled) return
    const onExit = () => {
      const payload = payloadOf({ completed: false })
      if (!payload) return
      const key = `${payload.segment_position}:${payload.offset_ms}:${payload.completed}`
      if (key !== lastSaved.current) saveProgressOnExit(storyId, payload)
    }
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') onExit()
    }
    window.addEventListener('pagehide', onExit)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('pagehide', onExit)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, payloadOf, storyId])

  // Ao terminar a história: marca como concluída (na última frase, no começo dela)
  const markCompleted = useCallback(
    (position: ListenPosition) => save({ completed: true, position }),
    [save],
  )

  return { markCompleted }
}
