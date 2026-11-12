import type { Density, FilterRules, Progression, SegmentType, WordLevel } from '../filters/api'
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

// ---------- curva de densidade crescente (US11, Cenário C): espelho do `DensityCurve` ----------
// A densidade do filtro é a FINAL. A curva começa em 1/5 dela e sobe em linha reta até ela no fim da história.

// Fração-alvo (0 a 1) na posição relativa `position` (0 = começo, 1 = fim)
export function curveTarget(density: Density, position: number): number {
  return ((DENSITY_SHARE[density] / 100) * (1 + 4 * position)) / 5
}

// Fração-alvo da frase `index` (de `total`) = numerador / (1000 * total), só com inteiros
function curveNumerator(density: Density, index: number, total: number): number {
  return DENSITY_SHARE[density] * (2 * total + 8 * index + 4)
}

// Fração-alvo de trocas da frase `index` (de `total`): a da curva, ou a densidade fixa
export function sentenceTarget(density: Density, progression: Progression | undefined, index: number, total: number) {
  if (progression === 'increasing') return curveNumerator(density, index, total) / (1000 * total)
  return DENSITY_SHARE[density] / 100
}

// Método do acumulador (mesma conta do `DensityCurve.select`): `sentences[k]` é a frase do candidato k
export function pickWithCurve(sentences: number[], total: number, density: Density): number[] {
  const whole = 1000 * total
  let accumulator = whole / 2
  const chosen: number[] = []
  sentences.forEach((index, k) => {
    accumulator += curveNumerator(density, index, total)
    if (accumulator >= whole) {
      chosen.push(k)
      accumulator -= whole
    }
  })
  return chosen
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

// Escolhe, de forma estável e espalhada pela história inteira, quais anotações viram troca
export function selectSwapIds(segments: StorySegment[], rules: FilterRules): Set<number> {
  const orderedSegments = [...segments].sort((a, b) => a.position - b.position)
  // Ordem de aparição: frase, depois posição na frase (faz parte do determinismo da escolha)
  const ordered = orderedSegments.flatMap((segment, sentence) =>
    [...segment.annotations]
      .sort((a, b) => a.en_start - b.en_start || a.id - b.id)
      .map((annotation) => ({ annotation, sentence })),
  )

  const selected = new Set<number>()
  for (const type of rules.segment_types) {
    const accepts = CANDIDATES[type]
    if (!accepts) continue
    const candidates = ordered.filter(({ annotation }) => isAligned(annotation) && accepts(annotation, rules))
    const indices =
      rules.progression === 'increasing'
        ? pickWithCurve(
            candidates.map((c) => c.sentence),
            orderedSegments.length,
            rules.density,
          )
        : pickEvenly(candidates.length, rules.density)
    indices.forEach((i) => selected.add(candidates[i].annotation.id))
  }
  return selected
}

// Fração (0 a 1) em porcentagem, com vírgula decimal: 0,07 -> "7%"; 0,175 -> "17,5%"
export function formatShare(share: number): string {
  return `${(share * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}
