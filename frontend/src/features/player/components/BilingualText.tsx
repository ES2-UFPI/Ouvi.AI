import { useEffect, useRef } from 'react'
import type { BaseLanguage } from '../../filters/api'
import type { StorySegment } from '../../stories/api'
import { buildParts } from '../buildParts'

interface BilingualTextProps {
  segments: StorySegment[]
  baseLanguage: BaseLanguage
  swapIds: ReadonlySet<number>
  // Frase que está tocando agora: ganha destaque e é rolada para a vista
  activeSegmentId?: number | null
}

export function BilingualText({ segments, baseLanguage, swapIds, activeSegmentId = null }: BilingualTextProps) {
  const activeRef = useRef<HTMLParagraphElement | null>(null)

  useEffect(() => {
    // jsdom não implementa scrollIntoView
    activeRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [activeSegmentId])

  // Os trechos trocados ficam no idioma oposto ao idioma base
  const swappedLanguage = baseLanguage === 'pt' ? 'en' : 'pt'
  const accent = swappedLanguage === 'en' ? 'var(--color-accent-en)' : 'var(--color-accent-pt)'

  return (
    <section
      aria-label="Texto da história com os trechos trocados"
      className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40 mt-6"
    >
      <div className="max-h-80 overflow-y-auto pr-2 space-y-3 text-text-primary leading-relaxed">
        {segments.map((segment) => (
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
            {buildParts(segment, baseLanguage, swapIds).map((part, i) =>
              part.swapped ? (
                <mark
                  key={i}
                  lang={swappedLanguage}
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
    </section>
  )
}