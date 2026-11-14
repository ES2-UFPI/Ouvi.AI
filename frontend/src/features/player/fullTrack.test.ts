import { describe, expect, it } from 'vitest'
import type { FullAudio } from './api'
import { segmentAfter, segmentAt, startOfPosition } from './fullTrack'

// Frases nas posições 0, 1 e 3 (a de posição 2 falhou e ficou de fora), cada uma com 2 s
const track: FullAudio = {
  url: 'http://api/audio/stream',
  expires_at: '',
  duration_ms: 6000,
  format: 'mp3',
  skipped: [30],
  segments: [
    { segment_id: 10, position: 0, start_ms: 0, duration_ms: 2000 },
    { segment_id: 20, position: 1, start_ms: 2000, duration_ms: 2000 },
    { segment_id: 40, position: 3, start_ms: 4000, duration_ms: 2000 },
  ],
}

describe('segmentAt', () => {
  it('acha a frase pelo ponto do áudio, incluindo as fronteiras', () => {
    expect(segmentAt(track, 0)?.segment_id).toBe(10)
    expect(segmentAt(track, 1999)?.segment_id).toBe(10)
    expect(segmentAt(track, 2000)?.segment_id).toBe(20)
    expect(segmentAt(track, 5500)?.segment_id).toBe(40)
  })

  it('depois do fim continua na última frase, e antes do começo não há frase', () => {
    expect(segmentAt(track, 99_000)?.segment_id).toBe(40)
    expect(segmentAt(track, -1)).toBeNull()
  })
})

describe('startOfPosition', () => {
  it('acha a frase pela posição', () => {
    expect(startOfPosition(track, 1)?.start_ms).toBe(2000)
  })

  it('se a frase falhou, vale a próxima que está no áudio', () => {
    expect(startOfPosition(track, 2)?.segment_id).toBe(40)
  })

  it('além da última frase, não há onde começar', () => {
    expect(startOfPosition(track, 9)).toBeNull()
  })
})

describe('segmentAfter', () => {
  it('devolve a frase seguinte, pulando as que ficaram de fora', () => {
    expect(segmentAfter(track, 0)?.segment_id).toBe(20)
    expect(segmentAfter(track, 1)?.segment_id).toBe(40)
  })

  it('na última frase não há seguinte', () => {
    expect(segmentAfter(track, 3)).toBeNull()
  })
})
