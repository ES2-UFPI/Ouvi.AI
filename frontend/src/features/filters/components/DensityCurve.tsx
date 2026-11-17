import { useId } from 'react'
import type { Density } from '../api'
import { DENSITY_LABELS } from '../labels'
import { curveTarget, DENSITY_SHARE, formatShare } from '../../player/swaps'

interface DensityCurveProps {
  // Densidade FINAL escolhida no filtro
  density: Density
}

// Área do desenho (unidades do viewBox) e a escala vertical: fixa na densidade mais alta, para a curva
// subir ou descer quando o usuário troca a densidade
const WIDTH = 300
const HEIGHT = 120
const PAD = { top: 10, right: 12, bottom: 22, left: 34 }
const MAX_SHARE = Math.max(...Object.values(DENSITY_SHARE)) / 100
const SAMPLES = 20

const x = (position: number) => PAD.left + position * (WIDTH - PAD.left - PAD.right)
const y = (share: number) => HEIGHT - PAD.bottom - (share / MAX_SHARE) * (HEIGHT - PAD.top - PAD.bottom)

// Prévia gráfica da densidade crescente (Cenário C): quanto inglês há em cada altura da história
export function DensityCurve({ density }: DensityCurveProps) {
  const titleId = useId()
  const descId = useId()
  const start = curveTarget(density, 0)
  const end = curveTarget(density, 1)
  const points = Array.from({ length: SAMPLES + 1 }, (_, i) => i / SAMPLES).map(
    (p) => `${x(p).toFixed(1)},${y(curveTarget(density, p)).toFixed(1)}`,
  )
  const area = `M${x(0)},${y(0)} L${points.join(' L')} L${x(1)},${y(0)} Z`
  const description = `O inglês começa em ${formatShare(start)} das palavras escolhidas e sobe até ${formatShare(end)} no final da história (densidade final ${DENSITY_LABELS[density].toLowerCase()}).`

  return (
    <figure className="mt-3">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={`${titleId} ${descId}`}
        className="w-full h-auto"
        data-testid="density-curve"
      >
        <title id={titleId}>Curva de densidade de inglês ao longo da história</title>
        <desc id={descId}>{description}</desc>
        {/* eixos: história (começo ao fim) e porcentagem de inglês */}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(0)} stroke="var(--color-border-subtle)" />
        <line x1={x(0)} y1={y(0)} x2={x(0)} y2={y(MAX_SHARE)} stroke="var(--color-border-subtle)" />
        <text x={x(0) - 4} y={y(MAX_SHARE) + 4} textAnchor="end" fontSize="9" fill="var(--color-text-muted)">
          {formatShare(MAX_SHARE)}
        </text>
        <text x={x(0) - 4} y={y(0)} textAnchor="end" fontSize="9" fill="var(--color-text-muted)">
          0%
        </text>
        <text x={x(0)} y={HEIGHT - 6} fontSize="9" fill="var(--color-text-muted)">
          Começo
        </text>
        <text x={x(1)} y={HEIGHT - 6} textAnchor="end" fontSize="9" fill="var(--color-text-muted)">
          Fim da história
        </text>
        <path d={area} fill="color-mix(in srgb, var(--color-accent-en) 18%, transparent)" />
        <polyline
          data-testid="density-curve-line"
          points={points.join(' ')}
          fill="none"
          stroke="var(--color-accent-en)"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx={x(0)} cy={y(start)} r="3" fill="var(--color-accent-en)" />
        <circle cx={x(1)} cy={y(end)} r="3" fill="var(--color-accent-en)" />
      </svg>
      {/* A mesma informação em texto, visível para todos (e lida pelos leitores de tela) */}
      <figcaption className="text-xs text-text-muted mt-1.5">{description}</figcaption>
    </figure>
  )
}
