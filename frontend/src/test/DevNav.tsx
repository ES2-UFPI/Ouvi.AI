import { Link } from 'react-router-dom'

const ROUTES = [
  { path: '/login', label: 'Login' },
  { path: '/cadastro', label: 'Cadastro' },
  { path: '/', label: 'Dashboard' },
  { path: '/filter', label: 'Filtro de Audição' },
  { path: '/player/material-teste-123', label: 'Player' },
]

export function DevNav() {
  return (
    <div className="min-h-screen bg-bg-deep p-8">
      <h1 className="font-display text-2xl text-text-primary mb-6">
        Navegação de desenvolvimento
      </h1>
      <div className="flex flex-col gap-3 max-w-xs">
        {ROUTES.map((route) => (
          <Link
            key={route.path}
            to={route.path}
            className="rounded-lg bg-bg-surface border border-border-subtle px-4 py-2.5 text-text-primary hover:border-accent-en transition-colors"
          >
            {route.label}
          </Link>
        ))}
      </div>
    </div>
	
  )
}