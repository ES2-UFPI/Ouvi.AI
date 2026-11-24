import type { SegmentAudioStatus } from './api'

// Regras da playlist de frases, sem React: dá para testar cada uma sozinha.
// Uma frase "pulada" é a que falhou (na geração ou ao buscar a URL) e não tem áudio para tocar.
export type IsSkipped = (segment: SegmentAudioStatus) => boolean

// As frases em ordem de posição na história (a API não garante a ordem)
export function sortByPosition(segments: readonly SegmentAudioStatus[]): SegmentAudioStatus[] {
  return [...segments].sort((a, b) => a.position - b.position)
}

// Índice da frase inicial: a primeira com a posição pedida ou depois dela (a primeira da lista, se não há)
export function startIndexFor(segments: readonly SegmentAudioStatus[], startPosition: number): number {
  return Math.max(0, segments.findIndex((s) => s.position >= startPosition))
}

// A partir do índice pedido, o primeiro que não é pulado (`segments.length` se não sobrou nenhuma)
export function skipFailed(segments: readonly SegmentAudioStatus[], from: number, isSkipped: IsSkipped): number {
  let index = from
  while (index < segments.length && isSkipped(segments[index])) index += 1
  return index
}

// A frase seguinte à atual, se ela já está pronta: serve para buscar a URL antes e trocar de frase sem pausa.
// Só a PRÓXIMA conta; se ela ainda está gerando, não adianta olhar as outras.
export function nextReadySegment(
  segments: readonly SegmentAudioStatus[],
  currentIndex: number,
  isSkipped: IsSkipped,
): SegmentAudioStatus | null {
  for (let i = currentIndex + 1; i < segments.length; i++) {
    if (isSkipped(segments[i])) continue
    return segments[i].status === 'ready' ? segments[i] : null
  }
  return null
}
