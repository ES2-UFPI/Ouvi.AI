import { describe, it, expect } from 'vitest'
import { buildParts } from './buildParts'

const segment = {
  id: 1,
  position: 0,
  text_en: 'He put on his coat.',
  text_pt: 'Ele vestiu o casaco.',
  annotations: [
    {
      id: 10, kind: 'phrasal_verb', lemma: 'put on',
      en_start: 3, en_end: 9, en_text: 'put on',
      pt_start: 4, pt_end: 10, pt_text: 'vestiu', extra: {},
    },
  ],
}

describe('buildParts', () => {
  it('troca o trecho no idioma base português', () => {
    expect(buildParts(segment, 'pt', new Set([10]))).toEqual([
      { text: 'Ele ', swapped: false },
      { text: 'put on', swapped: true },
      { text: ' o casaco.', swapped: false },
    ])
  })

  it('troca o trecho no idioma base inglês', () => {
    expect(buildParts(segment, 'en', new Set([10]))).toEqual([
      { text: 'He ', swapped: false },
      { text: 'vestiu', swapped: true },
      { text: ' his coat.', swapped: false },
    ])
  })

  it('devolve o texto inteiro quando nada é trocado', () => {
    expect(buildParts(segment, 'pt', new Set())).toEqual([
      { text: 'Ele vestiu o casaco.', swapped: false },
    ])
  })
})