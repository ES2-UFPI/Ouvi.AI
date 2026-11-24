import axios from 'axios'
import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { AuthLayout } from '../../../shared/components/AuthLayout'
import { TextField } from '../../../shared/components/TextField'
import { login } from '../api'
import { useAuthStore } from '../store'

export function LoginForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const setTokens = useAuthStore((s) => s.setTokens)
  // Vindo do cadastro, o estado traz `registered` e o e-mail; vindo de uma rota protegida, traz `from`
  const state = location.state as { from?: string; registered?: boolean; email?: string } | null
  const [email, setEmail] = useState(state?.email ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await login({ email, password })
      setTokens(data.access_token, data.refresh_token)
      const redirectTo = state?.from ?? '/'
      navigate(redirectTo, { replace: true })
    } catch (err) {
      // 401 = credencial errada; qualquer outra falha (rede, API fora do ar) tem mensagem própria
      setError(
        axios.isAxiosError(err) && err.response?.status === 401
          ? 'E-mail ou senha incorretos.'
          : 'Não foi possível entrar agora. Tente novamente em instantes.',
      )
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
          autoFocus={Boolean(state?.registered)}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && <p className="text-sm text-accent-pt mb-4">{error}</p>}
        {state?.registered && !error && (
          <p role="status" className="text-sm text-accent-en mb-4">
            Conta criada! Agora é só entrar com a sua senha.
          </p>
        )}

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