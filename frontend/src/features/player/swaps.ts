import type { Density, FilterRules, SegmentType, WordLevel } from '../filters/api'
import type { StoryAnnotation, StorySegment } from '../stories/api'

// Espelho de backend/app/modules/audio/composer: o que o player destaca precisa ser o que o áudio fala.
// Fração dos candidatos da história trocada em cada densidade, em centésimos (density.py: 0,15 / 0,35 / 0,60)
export const DENSITY_SHARE: Record<Density, number> = {
  low: 15,
  medium: 35,
  high: 60,
}

// Índices dos candidatos trocados, espaçados de forma regular (mesma conta do `pick_evenly`)
export function pickEvenly(total: number, density: Density): number[] {
  if (total === 0) return []
  // Arredonda a metade para cima, com inteiros para não ter erro de ponto flutuante
  const quantity = Math.min(total, Math.max(1, Math.floor((DENSITY_SHARE[density] * total + 50) / 100)))
  return Array.from({ length: quantity }, (_, i) => Math.floor(((2 * i + 1) * total) / (2 * quantity)))
}

// Nível pedido no filtro -> níveis das anotações que entram: o intermediário inclui as raras
const LEVELS_FOR_FILTER: Record<WordLevel, string[]> = {
  intermediate: ['intermediate', 'advanced'],
  advanced: ['advanced'],
}

const isAligned = (a: StoryAnnotation) => a.pt_start !== null && a.pt_end !== null && a.pt_text !== null

// Cada tipo de trecho do filtro escolhe as anotações candidatas (strategies.py)
const CANDIDATES: Partial<Record<SegmentType, (a: StoryAnnotation, rules: FilterRules) => boolean>> = {
  phrasal_verbs: (a) => a.kind === 'phrasal_verb',
  difficult_words: (a, rules) =>
    a.kind === 'difficult_word' &&
    LEVELS_FOR_FILTER[rules.word_level ?? 'intermediate'].includes(String(a.extra?.level)),
}

// Escolhe, de forma estável e espalhada pela história inteira, quais anotações viram troca
export function selectSwapIds(segments: StorySegment[], rules: FilterRules): Set<number> {
  // Ordem de aparição: frase, depois posição na frase (faz parte do determinismo da escolha)
  const ordered = [...segments]
    .sort((a, b) => a.position - b.position)
    .flatMap((segment) => [...segment.annotations].sort((a, b) => a.en_start - b.en_start || a.id - b.id))

  const selected = new Set<number>()
  for (const type of rules.segment_types) {
    const accepts = CANDIDATES[type]
    if (!accepts) continue
    const candidates = ordered.filter((a) => isAligned(a) && accepts(a, rules))
    pickEvenly(candidates.length, rules.density).forEach((i) => selected.add(candidates[i].id))
  }
  return selected
}
