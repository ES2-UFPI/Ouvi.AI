import { useEffect, useRef } from 'react'
import { History } from 'lucide-react'
import { formatTime } from '../formatTime'

interface ResumeCardProps {
  title: string
  // `position` da frase salva (o primeiro valor é 0) e o ponto dentro dela
  segmentPosition: number
  offsetMs: number
  // Total de frases da história, quando já se sabe
  total: number | null
  onContinue: () => void
  onRestart: () => void
}

// Cartão mostrado ao abrir uma história já começada. O clique também libera o som: os navegadores
// só deixam tocar sozinho depois de uma ação do usuário.
export function ResumeCard({ title, segmentPosition, offsetMs, total, onContinue, onRestart }: ResumeCardProps) {
  const continueButton = useRef<HTMLButtonElement>(null)
  // Quem usa o teclado já chega com o foco no botão principal
  useEffect(() => {
    continueButton.current?.focus()
  }, [])

  const sentence = segmentPosition + 1
  return (
    <section
      aria-labelledby="resume-title"
      className="rounded-2xl bg-bg-surface border border-border-subtle p-7 shadow-2xl shadow-black/40"
    >
      <div className="flex items-center gap-3 mb-4">
        <span
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-accent-en) 15%, transparent)',
            color: 'var(--color-accent-en)',
          }}
        >
          <History size={20} aria-hidden="true" />
        </span>
        <h2 id="resume-title" className="font-display text-2xl text-text-primary leading-tight">
          {title}
        </h2>
      </div>

      <p className="text-text-primary mb-1">
        Você parou na frase {sentence}
        {total ? ` de ${total}` : ''}.
      </p>
      <p className="text-sm text-text-muted mb-6">
        {offsetMs >= 1000 ? `Cerca de ${formatTime(offsetMs / 1000)} dentro da frase.` : 'No começo da frase.'}
      </p>

      <div className="flex flex-col sm:flex-row gap-3">
        <button
          ref={continueButton}
          type="button"
          onClick={onContinue}
          className="flex-1 rounded-xl py-3 font-medium text-bg-deep transition hover:brightness-110"
          style={{ backgroundColor: 'var(--color-accent-en)' }}
        >
          Continuar
        </button>
        <button
          type="button"
          onClick={onRestart}
          className="flex-1 rounded-xl py-3 font-medium text-text-primary border border-border-subtle transition hover:border-text-muted"
        >
          Recomeçar
        </button>
      </div>
    </section>
  )
}
