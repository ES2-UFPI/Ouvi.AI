import type { StorySegment } from '../stories/api'

export interface TextPart {
  text: string
  swapped: boolean
}

export function buildParts(
  segment: StorySegment,
  baseLanguage: 'pt' | 'en',
  swapIds: ReadonlySet<number>,
): TextPart[] {
  const base = baseLanguage === 'pt' ? segment.text_pt : segment.text_en

  const spans = segment.annotations
    .filter((a) => swapIds.has(a.id))
    .map((a) =>
      baseLanguage === 'pt'
        ? { start: a.pt_start, end: a.pt_end, replacement: a.en_text }
        : { start: a.en_start, end: a.en_end, replacement: a.pt_text },
    )
    .filter(
      (s): s is { start: number; end: number; replacement: string } =>
        s.start !== null && s.end !== null && s.replacement !== null,
    )
    .sort((a, b) => a.start - b.start)

  const parts: TextPart[] = []
  let cursor = 0
  for (const span of spans) {
    if (span.start < cursor) continue // sobreposição: ignora
    if (span.start > cursor) parts.push({ text: base.slice(cursor, span.start), swapped: false })
    parts.push({ text: span.replacement, swapped: true })
    cursor = span.end
  }
  if (cursor < base.length) parts.push({ text: base.slice(cursor), swapped: false })
  return parts
}