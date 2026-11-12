import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DensityIndicator } from './DensityIndicator'

const fases = (percents: number[]) => percents.map((percent) => ({ percent, candidates: 4, swapped: 1 }))

describe('DensityIndicator', () => {
  it('mostra a fração de cada terço, com vírgula decimal, e destaca o terço atual', () => {
    render(
      <DensityIndicator density="medium" progression="increasing" phases={fases([1750, 3500, 5250])} currentPhase={2} />,
    )
    expect(screen.getByText('Densidade média · crescente')).toBeInTheDocument()
    expect(screen.getByText('Início: 17,5%')).toBeInTheDocument()
    expect(screen.getByText('Fim: 52,5%').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('status')).toHaveTextContent('Agora: fim da história, 52,5% das trocas possíveis')
    expect(screen.getAllByText('1 de 4 trechos trocados')).toHaveLength(3)
  })

  it('densidade constante: barras iguais e sem terço atual antes de tocar', () => {
    render(<DensityIndicator density="low" progression="constant" phases={fases([1500, 1500, 1500])} currentPhase={null} />)
    expect(screen.getByText('Densidade baixa · constante')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    const alturas = screen.getAllByTestId('density-bar').map((b) => b.style.height)
    expect(new Set(alturas).size).toBe(1)
  })
})
