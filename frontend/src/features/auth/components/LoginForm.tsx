import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { AuthLayout } from '../../../shared/components/AuthLayout'
import { TextField } from '../../../shared/components/TextField'
import { login } from '../api'
import { useAuthStore } from '../store'

export function LoginForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const setToken = useAuthStore((s) => s.setToken)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await login({ email, password })
      setToken(data.access_token)
      const redirectTo = (location.state as { from?: string })?.from ?? '/'
      navigate(redirectTo, { replace: true })
    } catch {
      setError('E-mail ou senha incorretos.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h2 className="font-display text-2xl text-text-primary mb-1">Entrar</h2>
      <p className="text-text-muted text-sm mb-8">
        Continue de onde parou a sua última história.
      </p>

      <form onSubmit={handleSubmit}>
        <TextField
          id="email"
          label="E-mail"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <TextField
          id="password"
          label="Senha"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && <p className="text-sm text-accent-pt mb-4">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg py-2.5 font-medium text-bg-deep disabled:opacity-60 transition-opacity"
          style={{ backgroundColor: 'var(--color-accent-en)' }}
        >
          {loading ? 'Entrando...' : 'Entrar'}
        </button>
      </form>

      <p className="text-text-muted text-sm mt-6">
        Ainda não tem conta?{' '}
        <Link to="/cadastro" className="text-text-primary underline underline-offset-2">
          Criar conta
        </Link>
      </p>
    </AuthLayout>
  )
}