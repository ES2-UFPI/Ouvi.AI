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

// Cenário B: história em inglês com as palavras difíceis faladas em português
const englishBase: StorySegment[] = [
  {
    id: 2,
    position: 0,
    text_en: 'The fox was famished and weary.',
    text_pt: 'A raposa estava faminta e cansada.',
    annotations: [
      {
        id: 20, kind: 'difficult_word', lemma: 'famished',
        en_start: 12, en_end: 20, en_text: 'famished',
        pt_start: 16, pt_end: 23, pt_text: 'faminta', extra: { level: 'advanced', zipf: 2.1 },
      },
      {
        id: 21, kind: 'difficult_word', lemma: 'weary',
        en_start: 25, en_end: 30, en_text: 'weary',
        pt_start: 26, pt_end: 33, pt_text: 'cansada', extra: { level: 'intermediate', zipf: 3.2 },
      },
    ],
  },
]

describe('BilingualText com idioma base inglês', () => {
  it('destaca as palavras difíceis faladas em português, com a palavra em inglês na dica', () => {
    render(<BilingualText segments={englishBase} baseLanguage="en" swapIds={new Set([20, 21])} />)
    const destaque = screen.getByText('faminta')
    expect(destaque.tagName).toBe('MARK')
    expect(destaque).toHaveAttribute('lang', 'pt')
    expect(destaque).toHaveAttribute('title', 'Em inglês: famished')
    expect(screen.getByText('cansada').tagName).toBe('MARK')
    expect(destaque.closest('[lang="en"]')).not.toBeNull()
  })

  it('mostra a legenda com o idioma falado nos trechos', () => {
    render(<BilingualText segments={englishBase} baseLanguage="en" swapIds={new Set([20])} />)
    expect(screen.getByText('Trechos falados em português')).toBeInTheDocument()
  })

  it('lista "Nesta frase" as trocas da frase atual', () => {
    render(
      <BilingualText segments={englishBase} baseLanguage="en" swapIds={new Set([20])} activeSegmentId={2} />,
    )
    const lista = screen.getByRole('list', { name: 'Nesta frase' })
    expect(lista).toHaveTextContent('famished → faminta')
    expect(lista).not.toHaveTextContent('weary')
  })

  it('não mostra a lista quando não há frase tocando', () => {
    render(<BilingualText segments={englishBase} baseLanguage="en" swapIds={new Set([20])} />)
    expect(screen.queryByRole('list', { name: 'Nesta frase' })).toBeNull()
  })
})

describe('BilingualText no Cenário A', () => {
  it('continua mostrando o phrasal verb em inglês, com a legenda em inglês', () => {
    const { container } = render(
      <BilingualText segments={segments} baseLanguage="pt" swapIds={new Set([10])} activeSegmentId={1} />,
    )
    const destaque = container.querySelector('mark')
    expect(destaque).toHaveTextContent('put on')
    expect(destaque).toHaveAttribute('lang', 'en')
    expect(destaque).toHaveAttribute('title', 'Em português: vestiu')
    expect(screen.getByText('Trechos falados em inglês')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Nesta frase' })).toHaveTextContent('vestiu → put on')
  })
})