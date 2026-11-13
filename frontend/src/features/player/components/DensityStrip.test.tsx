import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DensityStrip } from './DensityStrip'

const PERFIL = [10, 20, 30, 40].map((id, i) => ({
  segment_id: id,
  position: i,
  candidates: 1,
  swapped: i % 2,
  target: 0.07 + 0.07 * i,
}))

describe('DensityStrip', () => {
  it('a altura de cada coluna acompanha a densidade da frase', () => {
    render(<DensityStrip profile={PERFIL} currentSegmentId={null} onSelect={() => {}} />)
    const alturas = screen.getAllByTestId('density-column').map((c) => parseFloat(c.style.height))
    expect(alturas).toEqual([...alturas].sort((a, b) => a - b))
    expect(alturas[3]).toBe(100)
    // sem frase tocando, mostra o intervalo da curva
    expect(screen.getByText('Inglês: de 7% a 28%')).toBeInTheDocument()
  })

  it('dá para pular de frase pelo teclado (Tab e Enter ou Espaço)', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<DensityStrip profile={PERFIL} currentSegmentId={10} onSelect={onSelect} />)

    await user.tab()
    expect(screen.getByRole('button', { name: /^Frase 1: 7% de inglês \(tocando agora\)/ })).toHaveFocus()
    await user.tab()
    await user.keyboard('{Enter}')
    expect(onSelect).toHaveBeenLastCalledWith(20)
    await user.tab()
    await user.keyboard(' ')
    expect(onSelect).toHaveBeenLastCalledWith(30)
  })

  it('sem frases não mostra nada', () => {
    const { container } = render(<DensityStrip profile={[]} currentSegmentId={null} onSelect={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
