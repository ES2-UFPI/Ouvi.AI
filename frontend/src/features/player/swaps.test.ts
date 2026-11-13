import { describe, it, expect } from 'vitest'
import { curveTarget, formatShare, pickEvenly, pickWithCurve, selectSwapIds, sentenceTarget } from './swaps'
import type { FilterRules } from '../filters/api'
import type { StoryAnnotation, StorySegment } from '../stories/api'

const annotation = (id: number, overrides: Partial<StoryAnnotation> = {}): StoryAnnotation => ({
  id, kind: 'phrasal_verb', lemma: 'x',
  en_start: id, en_end: id + 1, en_text: 'x',
  pt_start: 0, pt_end: 1, pt_text: 'y', extra: {},
  ...overrides,
})

const segmentWith = (annotations: StoryAnnotation[], position = 0): StorySegment => ({
  id: position + 1, position, text_en: 'a', text_pt: 'b', annotations,
})

const scenarioA = (density: FilterRules['density']): FilterRules => ({
  base_language: 'pt', segment_types: ['phrasal_verbs'], density,
})

describe('pickEvenly (mesma conta do backend)', () => {
  it('troca 15%, 35% e 60% dos candidatos, espaçados', () => {
    expect(pickEvenly(10, 'low')).toEqual([2, 7])
    expect(pickEvenly(10, 'medium')).toEqual([1, 3, 6, 8])
    expect(pickEvenly(10, 'high')).toEqual([0, 2, 4, 5, 7, 9])
  })

  it('troca pelo menos um quando há candidatos', () => {
    expect(pickEvenly(1, 'low')).toEqual([0])
    expect(pickEvenly(0, 'high')).toEqual([])
  })
})

describe('selectSwapIds', () => {
  const ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  const segments = [segmentWith(ids.slice(0, 6).map((id) => annotation(id))), segmentWith(ids.slice(6).map((id) => annotation(id)), 1)]

  it('Cenário A: escolhe os phrasal verbs pela densidade, na história inteira', () => {
    expect([...selectSwapIds(segments, scenarioA('medium'))].sort((a, b) => a - b)).toEqual([2, 4, 7, 9])
  })

  it('ignora anotações sem equivalente em português', () => {
    const semPt = annotation(9, { pt_start: null, pt_end: null, pt_text: null })
    expect([...selectSwapIds([segmentWith([semPt, annotation(1)])], scenarioA('high'))]).toEqual([1])
  })

  it('Cenário A ignora palavras difíceis', () => {
    const palavra = annotation(2, { kind: 'difficult_word', extra: { level: 'advanced' } })
    expect([...selectSwapIds([segmentWith([annotation(1), palavra])], scenarioA('high'))]).toEqual([1])
  })

  it('Cenário B: nível intermediário considera as duas faixas; avançado só as raras', () => {
    const palavras = [
      annotation(1, { kind: 'difficult_word', extra: { level: 'intermediate' } }),
      annotation(2, { kind: 'difficult_word', extra: { level: 'advanced' } }),
      annotation(3, { kind: 'phrasal_verb' }),
    ]
    const rules = (word_level: 'intermediate' | 'advanced'): FilterRules => ({
      base_language: 'en', segment_types: ['difficult_words'], density: 'high', word_level,
    })
    // 60% de 2 candidatos = 1 (o do meio da faixa)
    expect([...selectSwapIds([segmentWith(palavras)], rules('intermediate'))]).toEqual([2])
    expect([...selectSwapIds([segmentWith(palavras)], rules('advanced'))]).toEqual([2])
    expect(selectSwapIds([segmentWith(palavras.slice(0, 1))], rules('advanced')).size).toBe(0)
    expect([...selectSwapIds([segmentWith(palavras.slice(0, 1))], rules('intermediate'))]).toEqual([1])
  })

  it('sem anotações devolve conjunto vazio', () => {
    expect(selectSwapIds([], scenarioA('high')).size).toBe(0)
  })
})

// Mesmos valores de backend/tests/test_density_curve.py: o player precisa destacar o que o áudio fala
describe('densidade crescente (espelho do DensityCurve)', () => {
  const umaPorFrase = (total: number) => Array.from({ length: total }, (_, i) => i)

  it('a curva começa em 1/5 da densidade final e chega a ela no fim', () => {
    expect(curveTarget('medium', 0)).toBeCloseTo(0.07)
    expect(curveTarget('medium', 1)).toBeCloseTo(0.35)
    expect(sentenceTarget('medium', 'increasing', 9, 10)).toBeCloseTo(curveTarget('medium', 0.95))
    expect(sentenceTarget('medium', undefined, 0, 10)).toBe(0.35)
  })

  it('dá os mesmos índices do backend (método do acumulador)', () => {
    expect(pickWithCurve(umaPorFrase(30), 30, 'low')).toEqual([9, 20, 28])
    expect(pickWithCurve(umaPorFrase(30), 30, 'medium')).toEqual([5, 11, 16, 20, 24, 27])
    expect(pickWithCurve(umaPorFrase(30), 30, 'high')).toEqual([3, 8, 11, 14, 17, 19, 21, 24, 25, 27, 29])
  })

  it('histórias curtas ou sem candidatos não dão erro', () => {
    expect(pickWithCurve([], 3, 'high')).toEqual([])
    expect(pickWithCurve([0], 1, 'low')).toEqual([])
    expect(pickWithCurve([0, 0, 1, 2], 3, 'high')).toEqual([2])
  })

  it('Cenário C: só as palavras raras, com a curva pela posição das frases', () => {
    const frases = Array.from({ length: 30 }, (_, i) =>
      segmentWith(
        [
          annotation(i + 1, { kind: 'difficult_word', extra: { level: 'advanced' } }),
          annotation(100 + i, { kind: 'difficult_word', extra: { level: 'intermediate' }, en_start: 50 }),
        ],
        i,
      ),
    )
    const rules: FilterRules = {
      base_language: 'pt', segment_types: ['advanced_vocabulary'], density: 'medium', progression: 'increasing',
    }
    expect([...selectSwapIds(frases, rules)].sort((a, b) => a - b)).toEqual([6, 12, 17, 21, 25, 28])
    // fora de ordem dá o mesmo resultado: a posição é a da frase
    expect(selectSwapIds([...frases].reverse(), rules)).toEqual(selectSwapIds(frases, rules))
    // sem a progressão, volta à densidade fixa (a mesma de antes da US11)
    const { progression: _, ...fixa } = rules
    expect(selectSwapIds(frases, fixa).size).toBe(pickEvenly(30, 'medium').length)
  })

  it('formata porcentagens com vírgula decimal', () => {
    expect(formatShare(0.07)).toBe('7%')
    expect(formatShare(0.175)).toBe('17,5%')
  })
})
