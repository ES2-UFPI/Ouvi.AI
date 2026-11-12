import type { Density, FilterRules, SegmentType, WordLevel } from '../filters/api'
import type { StoryAnnotation, StorySegment } from '../stories/api'

// Espelho de backend/app/modules/audio/composer: o que o player destaca precisa ser o que o áudio fala.
// Fração dos candidatos da história trocada em cada densidade, em centésimos (density.py: 0,15 / 0,35 / 0,60)
export const DENSITY_SHARE: Record<Density, number> = {
  low: 15,
  medium: 35,
  high: 60,
}

// Densidade crescente (US11): peso de cada terço da história, em % da densidade (início, meio e fim)
export const PHASE_WEIGHTS = [50, 100, 150] as const
const PHASES = PHASE_WEIGHTS.length

// Índices dos candidatos trocados, espaçados de forma regular (mesma conta do `pick_evenly`)
export function pickEvenly(total: number, density: Density): number[] {
  if (total === 0) return []
  // Arredonda a metade para cima, com inteiros para não ter erro de ponto flutuante
  const quantity = Math.min(total, Math.max(1, Math.floor((DENSITY_SHARE[density] * total + 50) / 100)))
  return Array.from({ length: quantity }, (_, i) => Math.floor(((2 * i + 1) * total) / (2 * quantity)))
}

// Terço da história (0 = início, 1 = meio, 2 = fim) da frase de índice `index` entre `total` frases
export function phaseOf(index: number, total: number): number {
  return Math.floor((PHASES * index) / total)
}

// Fração trocada no terço, em centésimos de ponto percentual (média no fim = 5250 = 52,5%)
export function phasePercent(density: Density, phase: number): number {
  return DENSITY_SHARE[density] * PHASE_WEIGHTS[phase]
}

// Mesma conta do `pick_increasing`: em cada terço, densidade x peso, espaçados dentro do terço
export function pickIncreasing(phases: number[], density: Density): number[] {
  const chosen: number[] = []
  for (let phase = 0; phase < PHASES; phase++) {
    const indices = phases.flatMap((p, i) => (p === phase ? [i] : []))
    const total = indices.length
    const quantity = Math.min(total, Math.floor((phasePercent(density, phase) * total + 5000) / 10000))
    for (let i = 0; i < quantity; i++) chosen.push(indices[Math.floor(((2 * i + 1) * total) / (2 * quantity))])
  }
  if (chosen.length === 0 && phases.length > 0) {
    // Pelo menos uma troca: a do meio do último terço com candidatos
    const lastPhase = Math.max(...phases)
    const last = phases.flatMap((p, i) => (p === lastPhase ? [i] : []))
    chosen.push(last[Math.floor(last.length / 2)])
  }
  return chosen.sort((a, b) => a - b)
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
  // Cenário C: as mesmas anotações de palavras difíceis, só as raras (nível avançado)
  advanced_vocabulary: (a) => a.kind === 'difficult_word' && a.extra?.level === 'advanced',
}

const sortedSegments = (segments: StorySegment[]) => [...segments].sort((a, b) => a.position - b.position)

// Terço da história de cada frase (pela posição): usado pela curva e pelo indicador de densidade
export function segmentPhases(segments: StorySegment[]): Map<number, number> {
  const ordered = sortedSegments(segments)
  return new Map(ordered.map((segment, index) => [segment.id, phaseOf(index, ordered.length)]))
}

// Candidatos de cada tipo do filtro, em ordem de aparição, com o terço de cada um
function candidatesByType(segments: StorySegment[], rules: FilterRules) {
  const phases = segmentPhases(segments)
  // Ordem de aparição: frase, depois posição na frase (faz parte do determinismo da escolha)
  const ordered = sortedSegments(segments).flatMap((segment) =>
    [...segment.annotations]
      .sort((a, b) => a.en_start - b.en_start || a.id - b.id)
      .map((annotation) => ({ annotation, phase: phases.get(segment.id) ?? 0 })),
  )
  return rules.segment_types.map((type) => {
    const accepts = CANDIDATES[type]
    return accepts ? ordered.filter(({ annotation }) => isAligned(annotation) && accepts(annotation, rules)) : []
  })
}

// Escolhe, de forma estável e espalhada pela história inteira, quais anotações viram troca
export function selectSwapIds(segments: StorySegment[], rules: FilterRules): Set<number> {
  const selected = new Set<number>()
  for (const candidates of candidatesByType(segments, rules)) {
    const indices =
      rules.progression === 'increasing'
        ? pickIncreasing(
            candidates.map((c) => c.phase),
            rules.density,
          )
        : pickEvenly(candidates.length, rules.density)
    indices.forEach((i) => selected.add(candidates[i].annotation.id))
  }
  return selected
}

export interface DensityPhase {
  // Fração da densidade neste terço, em centésimos de ponto percentual (3500 = 35%)
  percent: number
  candidates: number
  swapped: number
}

// Resumo da densidade por terço da história, para o indicador do player. Na densidade constante, os três
// terços têm a mesma fração; na crescente, ela sobe do início ao fim.
export function densityPhases(segments: StorySegment[], rules: FilterRules, swapIds: ReadonlySet<number>): DensityPhase[] {
  const increasing = rules.progression === 'increasing'
  const phases: DensityPhase[] = PHASE_WEIGHTS.map((_, phase) => ({
    percent: increasing ? phasePercent(rules.density, phase) : DENSITY_SHARE[rules.density] * 100,
    candidates: 0,
    swapped: 0,
  }))
  const seen = new Set<number>()
  for (const candidates of candidatesByType(segments, rules)) {
    for (const { annotation, phase } of candidates) {
      if (seen.has(annotation.id)) continue
      seen.add(annotation.id)
      phases[phase].candidates++
      if (swapIds.has(annotation.id)) phases[phase].swapped++
    }
  }
  return phases
}
