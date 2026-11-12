import { describe, it, expect } from 'vitest'
import { densityPhases, phaseOf, pickEvenly, pickIncreasing, segmentPhases, selectSwapIds } from './swaps'
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
describe('densidade crescente (espelho do pick_increasing)', () => {
  const tercos = (total: number) => Array.from({ length: total }, (_, i) => phaseOf(i, total))
  const porTerco = (fases: number[], escolhidos: number[]) =>
    [0, 1, 2].map((t) => escolhidos.filter((i) => fases[i] === t).length)

  it('divide a história em terços pela posição', () => {
    expect(tercos(10)).toEqual([0, 0, 0, 0, 1, 1, 1, 2, 2, 2])
  })

  it('dá os mesmos índices do backend', () => {
    const fases = tercos(30)
    expect(pickIncreasing(fases, 'low')).toEqual([5, 12, 17, 22, 27])
    expect(porTerco(fases, pickIncreasing(fases, 'medium'))).toEqual([2, 4, 5])
    expect(porTerco(fases, pickIncreasing(fases, 'high'))).toEqual([3, 6, 9])
  })

  it('troca pelo menos um quando há candidatos', () => {
    expect(pickIncreasing([0, 0, 1], 'low')).toEqual([2])
    expect(pickIncreasing([], 'high')).toEqual([])
  })

  it('Cenário C: só as palavras raras, com a curva aplicada por terço da história', () => {
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
    const ids = selectSwapIds(frases, rules)
    expect([...ids].every((id) => id <= 30)).toBe(true)
    expect(porTerco(tercos(30), [...ids].map((id) => id - 1))).toEqual([2, 4, 5])
    // sem a progressão, volta à densidade constante (mesmo resultado de antes da US11)
    const { progression: _, ...constante } = rules
    expect(selectSwapIds(frases, constante).size).toBe(pickEvenly(30, 'medium').length)

    const fases = densityPhases(frases, rules, ids)
    expect(fases.map((f) => f.percent)).toEqual([1750, 3500, 5250])
    expect(fases.map((f) => f.candidates)).toEqual([10, 10, 10])
    expect(fases.map((f) => f.swapped)).toEqual([2, 4, 5])
  })

  it('na densidade constante os três terços têm a mesma fração', () => {
    const fases = densityPhases([segmentWith([annotation(1)])], scenarioA('low'), new Set([1]))
    expect(fases.map((f) => f.percent)).toEqual([1500, 1500, 1500])
    expect(segmentPhases([segmentWith([], 1), segmentWith([], 0)]).get(1)).toBe(0)
  })
})
