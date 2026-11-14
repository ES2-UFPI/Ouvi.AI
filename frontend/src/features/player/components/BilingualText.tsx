import { useEffect, useRef } from 'react'
import { Play } from 'lucide-react'
import type { BaseLanguage } from '../../filters/api'
import type { StorySegment } from '../../stories/api'
import { buildParts } from '../buildParts'

interface BilingualTextProps {
  segments: StorySegment[]
  baseLanguage: BaseLanguage
  swapIds: ReadonlySet<number>
  // Frase que está tocando agora: ganha destaque e é rolada para a vista
  activeSegmentId?: number | null
  // Com isto, cada frase ganha um botão para ouvir a partir dela (voltar até uma palavra)
  onSelectSegment?: (segmentId: number) => void
}

const LANGUAGE_NAMES: Record<BaseLanguage, string> = { pt: 'português', en: 'inglês' }

export function BilingualText({
  segments,
  baseLanguage,
  swapIds,
  activeSegmentId = null,
  onSelectSegment,
}: BilingualTextProps) {
  const activeRef = useRef<HTMLParagraphElement | null>(null)

  useEffect(() => {
    // jsdom não implementa scrollIntoView
    activeRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [activeSegmentId])

  // Os trechos trocados ficam no idioma oposto ao idioma base
  const swappedLanguage = baseLanguage === 'pt' ? 'en' : 'pt'
  const accent = swappedLanguage === 'en' ? 'var(--color-accent-en)' : 'var(--color-accent-pt)'

  // Glossário da frase atual: cada trecho trocado e o que foi falado no lugar dele
  const activeSegment = segments.find((s) => s.id === activeSegmentId)
  const activeSwaps = activeSegment
    ? buildParts(activeSegment, baseLanguage, swapIds).filter((part) => part.swapped)
    : []

  return (
    <section
      aria-label="Texto da história com os trechos trocados"
      className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40 mt-6"
    >
      <p className="flex items-center gap-2 text-xs text-text-muted mb-4">
        <span
          aria-hidden="true"
          className="inline-block w-3 h-3 rounded"
          style={{ backgroundColor: `color-mix(in srgb, ${accent} 28%, transparent)`, boxShadow: `inset 0 -2px 0 ${accent}` }}
        />
        Trechos falados em {LANGUAGE_NAMES[swappedLanguage]}
      </p>
      <div lang={baseLanguage} className="max-h-80 overflow-y-auto pr-2 space-y-3 text-text-primary leading-relaxed">
        {segments.map((segment, index) => (
          <p
            key={segment.id}
            ref={segment.id === activeSegmentId ? activeRef : undefined}
            aria-current={segment.id === activeSegmentId ? 'true' : undefined}
            className="rounded-lg px-2 -mx-2 transition-colors"
            style={
              segment.id === activeSegmentId
                ? { backgroundColor: 'color-mix(in srgb, var(--color-text-primary) 8%, transparent)' }
                : undefined
            }
          >
            {onSelectSegment && (
              <button
                type="button"
                onClick={() => onSelectSegment(segment.id)}
                aria-label={`Ouvir a partir da frase ${index + 1}`}
                className="inline-flex items-center justify-center w-5 h-5 mr-1.5 align-middle rounded-full text-text-muted hover:text-text-primary focus-visible:ring-2 focus-visible:ring-accent-en transition-colors"
              >
                <Play size={11} fill="currentColor" aria-hidden="true" />
              </button>
            )}
            {buildParts(segment, baseLanguage, swapIds).map((part, i) =>
              part.swapped ? (
                <mark
                  key={i}
                  lang={swappedLanguage}
                  title={`Em ${LANGUAGE_NAMES[baseLanguage]}: ${part.original}`}
                  className="rounded px-1 text-text-primary"
                  style={{
                    backgroundColor: `color-mix(in srgb, ${accent} 28%, transparent)`,
                    boxShadow: `inset 0 -2px 0 ${accent}`,
                  }}
                >
                  {part.text}
                </mark>
              ) : (
                <span key={i}>{part.text}</span>
              ),
            )}
          </p>
        ))}
      </div>
      {activeSwaps.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border-subtle">
          <p className="text-xs uppercase tracking-wider text-text-muted mb-2">Nesta frase</p>
          <ul aria-label="Nesta frase" className="space-y-1 text-sm text-text-primary">
            {activeSwaps.map((part, i) => (
              <li key={i}>
                <span lang={baseLanguage}>{part.original}</span>
                <span className="text-text-muted"> → </span>
                <span lang={swappedLanguage} style={{ color: accent }}>
                  {part.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
