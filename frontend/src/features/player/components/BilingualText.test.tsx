import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BilingualText } from './BilingualText'
import type { StorySegment } from '../../stories/api'

const segments: StorySegment[] = [
  {
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
  },
]

describe('BilingualText', () => {
  it('destaca em inglês o trecho trocado quando a base é português', () => {
    render(<BilingualText segments={segments} baseLanguage="pt" swapIds={new Set([10])} />)
    const destaque = screen.getByText('put on')
    expect(destaque.tagName).toBe('MARK')
    expect(destaque).toHaveAttribute('lang', 'en')
  })

  it('destaca em português o trecho trocado quando a base é inglês', () => {
    render(<BilingualText segments={segments} baseLanguage="en" swapIds={new Set([10])} />)
    const destaque = screen.getByText('vestiu')
    expect(destaque.tagName).toBe('MARK')
    expect(destaque).toHaveAttribute('lang', 'pt')
  })

  it('mostra a frase inteira, sem destaque, quando nada é trocado', () => {
    const { container } = render(
      <BilingualText segments={segments} baseLanguage="pt" swapIds={new Set()} />,
    )
    expect(screen.getByText('Ele vestiu o casaco.')).toBeInTheDocument()
    expect(container.querySelector('mark')).toBeNull()
  })
})