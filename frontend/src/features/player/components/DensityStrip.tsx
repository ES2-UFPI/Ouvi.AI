import type { DensityPoint } from '../../stories/api'
import { formatShare } from '../swaps'

interface DensityStripProps {
  // Perfil de densidade da prévia (GET /stories/{id}/preview), uma entrada por frase
  profile: DensityPoint[]
  // Frase que está tocando; null antes de começar ou no fim
  currentSegmentId: number | null
  // Leva o player para a frase escolhida
  onSelect: (segmentId: number) => void
}

// Faixa da densidade crescente (Cenário C): uma coluna por frase, com altura proporcional ao inglês daquela
// parte da história. A coluna da frase atual fica destacada; clicar (ou Enter/Espaço) pula para a frase.
export function DensityStrip({ profile, currentSegmentId, onSelect }: DensityStripProps) {
  if (profile.length === 0) return null
  const highest = Math.max(...profile.map((p) => p.target)) || 1
  const currentIndex = profile.findIndex((p) => p.segment_id === currentSegmentId)
  const current = currentIndex >= 0 ? profile[currentIndex] : null
  const swapped = profile.reduce((sum, p) => sum + p.swapped, 0)
  const candidates = profile.reduce((sum, p) => sum + p.candidates, 0)
  const summary =
    `O inglês começa em ${formatShare(profile[0].target)} e sobe até ` +
    `${formatShare(profile[profile.length - 1].target)} no final da história. ` +
    `${swapped} de ${candidates} palavras de vocabulário avançado são faladas em inglês.`

  return (
    <section
      aria-label="Densidade de inglês por frase"
      className="rounded-2xl bg-bg-surface border border-border-subtle px-7 py-4 shadow-2xl shadow-black/40 mt-3"
    >
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <p className="text-xs uppercase tracking-wider text-text-muted">Densidade crescente</p>
        <p aria-live="polite" className="text-xs text-text-primary">
          {current
            ? `Inglês nesta parte: ${formatShare(current.target)}`
            : `Inglês: de ${formatShare(profile[0].target)} a ${formatShare(profile[profile.length - 1].target)}`}
        </p>
      </div>
      {/* Alternativa em texto da faixa inteira para leitores de tela */}
      <p className="sr-only">{summary}</p>
      <div className="flex items-end gap-px h-10" role="group" aria-label="Frases da história">
        {profile.map((point, index) => {
          const active = index === currentIndex
          return (
            <button
              key={point.segment_id}
              type="button"
              onClick={() => onSelect(point.segment_id)}
              aria-current={active ? 'true' : undefined}
              aria-label={`Frase ${index + 1}: ${formatShare(point.target)} de inglês${
                point.swapped ? `, ${point.swapped} ${point.swapped === 1 ? 'palavra' : 'palavras'} em inglês` : ''
              }${active ? ' (tocando agora)' : ''}`}
              title={`Frase ${index + 1}: ${formatShare(point.target)} de inglês`}
              className="flex-1 h-full flex items-end rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-en cursor-pointer"
            >
              <span
                data-testid="density-column"
                className="block w-full rounded-sm transition-colors"
                style={{
                  height: `${Math.max(10, (point.target / highest) * 100)}%`,
                  backgroundColor: active
                    ? 'var(--color-text-primary)'
                    : point.swapped
                      ? 'var(--color-accent-en)'
                      : 'color-mix(in srgb, var(--color-accent-en) 30%, transparent)',
                }}
              />
            </button>
          )
        })}
      </div>
    </section>
  )
}
