import { describe, it, expect } from 'vitest'
import { selectSwapIds } from './swaps'
import type { StoryAnnotation, StorySegment } from '../stories/api'

const annotation = (id: number): StoryAnnotation => ({
  id, kind: 'phrasal_verb', lemma: 'x',
  en_start: 0, en_end: 1, en_text: 'x',
  pt_start: 0, pt_end: 1, pt_text: 'y', extra: {},
})

const segmentWith = (ids: number[]): StorySegment => ({
  id: 1, position: 0, text_en: 'a', text_pt: 'b', annotations: ids.map(annotation),
})

describe('selectSwapIds', () => {
  const segments = [segmentWith([1, 2, 3, 4]), segmentWith([5, 6])]

  it('densidade alta troca todos', () => {
    expect([...selectSwapIds(segments, 'high')]).toEqual([1, 2, 3, 4, 5, 6])
  })

  it('densidade média troca 2 de cada 3', () => {
    expect([...selectSwapIds(segments, 'medium')]).toEqual([2, 3, 5, 6])
  })

  it('densidade baixa troca 1 de cada 3', () => {
    expect([...selectSwapIds(segments, 'low')]).toEqual([3, 6])
  })

  it('ignora anotações sem equivalente em português', () => {
    const semPt = { ...annotation(9), pt_start: null, pt_end: null, pt_text: null }
    const seg = { ...segmentWith([1]), annotations: [semPt, annotation(1)] }
    expect([...selectSwapIds([seg], 'high')]).toEqual([1])
  })

  it('sem anotações devolve conjunto vazio', () => {
    expect(selectSwapIds([], 'high').size).toBe(0)
  })
})