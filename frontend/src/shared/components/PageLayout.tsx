import type { ReactNode } from 'react'

// Moldura das telas logadas: conteúdo centralizado sobre um brilho suave nas cores do projeto
export function PageLayout({ children }: { children: ReactNode }) {
  return (
    <main
      className="min-h-screen flex items-center justify-center bg-bg-deep px-6 py-10"
      style={{
        backgroundImage:
          'radial-gradient(60% 50% at 20% 0%, color-mix(in srgb, var(--color-accent-pt) 10%, transparent), transparent), radial-gradient(60% 50% at 80% 100%, color-mix(in srgb, var(--color-accent-en) 10%, transparent), transparent)',
      }}
    >
      <div className="w-full max-w-md">{children}</div>
    </main>
  )
}
