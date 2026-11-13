import type { FullAudio, TrackSegment } from './api'

// A frase que está tocando no instante `ms` do áudio único (a última cujo início já passou)
export function segmentAt(track: FullAudio, ms: number): TrackSegment | null {
  let found: TrackSegment | null = null
  for (const segment of track.segments) {
    if (segment.start_ms <= ms) found = segment
    else break
  }
  return found
}

// Início da frase de `position`; se ela ficou de fora (falhou), o da próxima que está no áudio
export function startOfPosition(track: FullAudio, position: number): TrackSegment | null {
  return track.segments.find((s) => s.position >= position) ?? null
}

// A frase que vem depois da de `position` no áudio, ou null se ela é a última
export function segmentAfter(track: FullAudio, position: number): TrackSegment | null {
  return track.segments.find((s) => s.position > position) ?? null
}
