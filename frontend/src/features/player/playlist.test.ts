import { describe, expect, it } from 'vitest'
import type { GenerationState, SegmentAudioStatus } from './api'
import { nextReadySegment, skipFailed, sortByPosition, startIndexFor } from './playlist'

const segmento = (position: number, status: GenerationState = 'ready'): SegmentAudioStatus => ({
  segment_id: position + 100,
  position,
  status,
  duration_ms: status === 'ready' ? 1000 : null,
  error: status === 'failed' ? 'TTS falhou' : null,
})

const falhou = (s: SegmentAudioStatus) => s.status === 'failed'

describe('sortByPosition', () => {
  it('ordena pela posição e não altera a lista original', () => {
    const original = [segmento(2), segmento(0), segmento(1)]
    expect(sortByPosition(original).map((s) => s.position)).toEqual([0, 1, 2])
    expect(original.map((s) => s.position)).toEqual([2, 0, 1])
  })

  it('lista vazia continua vazia', () => {
    expect(sortByPosition([])).toEqual([])
  })
})

describe('startIndexFor', () => {
  const lista = [segmento(0), segmento(1), segmento(3)] // a frase de posição 2 não existe

  it('acha a frase pela posição', () => {
    expect(startIndexFor(lista, 1)).toBe(1)
  })

  it('se a posição não existe, vale a próxima', () => {
    expect(startIndexFor(lista, 2)).toBe(2)
  })

  it('além da última frase, volta para a primeira', () => {
    expect(startIndexFor(lista, 9)).toBe(0)
  })

  it('sem frases ainda, começa em 0', () => {
    expect(startIndexFor([], 4)).toBe(0)
  })
})

describe('skipFailed', () => {
  const lista = [segmento(0), segmento(1, 'failed'), segmento(2, 'failed'), segmento(3), segmento(4, 'failed')]

  it('mantém o índice se a frase não foi pulada', () => {
    expect(skipFailed(lista, 0, falhou)).toBe(0)
  })

  it('pula as que falharam em sequência', () => {
    expect(skipFailed(lista, 1, falhou)).toBe(3)
  })

  it('se só sobraram falhas até o fim, devolve o tamanho da lista (fim da história)', () => {
    expect(skipFailed(lista, 4, falhou)).toBe(5)
  })

  it('um índice além do fim fica como está', () => {
    expect(skipFailed(lista, 5, falhou)).toBe(5)
  })
})

describe('nextReadySegment', () => {
  it('devolve a próxima frase quando ela já está pronta', () => {
    const lista = [segmento(0), segmento(1), segmento(2)]
    expect(nextReadySegment(lista, 0, falhou)?.position).toBe(1)
  })

  it('pula as que falharam e olha a primeira que sobrou', () => {
    const lista = [segmento(0), segmento(1, 'failed'), segmento(2)]
    expect(nextReadySegment(lista, 0, falhou)?.position).toBe(2)
  })

  it('se a próxima ainda está gerando, não adianta olhar as outras', () => {
    const lista = [segmento(0), segmento(1, 'generating'), segmento(2)]
    expect(nextReadySegment(lista, 0, falhou)).toBeNull()
    expect(nextReadySegment([segmento(0), segmento(1, 'pending')], 0, falhou)).toBeNull()
  })

  it('na última frase, ou se só restam falhas, não há próxima', () => {
    expect(nextReadySegment([segmento(0), segmento(1)], 1, falhou)).toBeNull()
    expect(nextReadySegment([segmento(0), segmento(1, 'failed')], 0, falhou)).toBeNull()
  })
})
