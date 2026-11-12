import type { Density, Progression } from '../../filters/api'
import { DENSITY_LABELS, PHASE_LABELS, PROGRESSION_LABELS } from '../../filters/labels'
import type { DensityPhase } from '../swaps'

interface DensityIndicatorProps {
  density: Density
  progression: Progression
  phases: DensityPhase[]
  // Terço da história da frase que está tocando (0 = início); null antes de começar ou no fim
  currentPhase: number | null
}

// 3500 (centésimos de ponto percentual) -> "35%"; 5250 -> "52,5%"
function formatPercent(value: number): string {
  return `${(value / 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}

// Mostra quanto do áudio muda de idioma em cada terço da história e em qual terço o ouvinte está
export function DensityIndicator({ density, progression, phases, currentPhase }: DensityIndicatorProps) {
  const highest = Math.max(...phases.map((p) => p.percent), 1)
  const current = currentPhase !== null ? phases[currentPhase] : undefined

  return (
    <section
      aria-label="Indicador de densidade"
      className="rounded-2xl bg-bg-surface border border-border-subtle px-7 py-5 shadow-2xl shadow-black/40 mt-6"
    >
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <p className="text-xs uppercase tracking-wider text-text-muted">
          Densidade {DENSITY_LABELS[density].toLowerCase()} · {PROGRESSION_LABELS[progression].toLowerCase()}
        </p>
        {current && currentPhase !== null && (
          <p role="status" className="text-xs text-text-primary">
            Agora: {PHASE_LABELS[currentPhase].toLowerCase()} da história, {formatPercent(current.percent)} das trocas
            possíveis
          </p>
        )}
      </div>
      <ol className="grid grid-cols-3 gap-3 items-end">
        {phases.map((phase, index) => {
          const active = index === currentPhase
          return (
            <li key={PHASE_LABELS[index]} aria-current={active ? 'step' : undefined} className="flex flex-col gap-1.5">
              <div className="h-12 flex items-end">
                <div
                  data-testid="density-bar"
                  className="w-full rounded-md transition-colors"
                  style={{
                    height: `${Math.max(8, (phase.percent / highest) * 100)}%`,
                    backgroundColor: active ? 'var(--color-accent-en)' : 'var(--color-border-subtle)',
                  }}
                />
              </div>
              <span className={`text-xs ${active ? 'text-text-primary font-medium' : 'text-text-muted'}`}>
                {PHASE_LABELS[index]}: {formatPercent(phase.percent)}
              </span>
              <span className="text-[11px] text-text-muted">
                {phase.swapped} de {phase.candidates} {phase.candidates === 1 ? 'trecho trocado' : 'trechos trocados'}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
