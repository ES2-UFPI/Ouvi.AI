import { ReactNode } from 'react'

function Waveform() {
  const heights = [18, 34, 22, 46, 28, 52, 20, 40, 30, 58, 24, 36, 44, 20, 32]
  return (
    <div className="flex items-end gap-1.5 h-16">
      {heights.map((h, i) => (
        <div
          key={i}
          className="w-1.5 rounded-full"
          style={{
            height: `${h}px`,
            backgroundColor: i % 2 === 0 ? 'var(--color-accent-pt)' : 'var(--color-accent-en)',
            opacity: i % 5 === 0 ? 0.9 : 0.55,
          }}
        />
      ))}
    </div>
  )
}

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-bg-deep">
      <aside className="lg:w-[42%] px-8 py-10 lg:py-16 flex flex-col justify-between border-b lg:border-b-0 lg:border-r border-border-subtle">
        <div>
          <p className="font-display text-2xl text-text-primary">Ouvi.AI</p>
        </div>
        <div className="mt-10 lg:mt-0">
          <Waveform />
          <h1 className="font-display text-3xl lg:text-4xl text-text-primary mt-6 max-w-sm leading-tight">
            A mesma história,{' '}
            <span style={{ color: 'var(--color-accent-pt)' }}>em português</span>{' '}
            ou{' '}
            <span style={{ color: 'var(--color-accent-en)' }}>em inglês</span>.
          </h1>
          <p className="text-text-muted mt-4 max-w-xs text-sm">
            Troque de idioma a qualquer momento da faixa, sem perder a voz do narrador.
          </p>
        </div>
        <div className="hidden lg:block text-text-muted text-sm">
          Aprenda ouvindo histórias
        </div>
      </aside>

      <main className="flex-1 flex items-center justify-center px-6 py-12 lg:py-16">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  )
}