import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../../../shared/components/AuthLayout'
import { TextField } from '../../../shared/components/TextField'
import { register } from '../api'

export function RegisterForm() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await register({ name, email, password })
      navigate('/login')
    } catch {
      setError('Não foi possível criar sua conta. Verifique os dados e tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <h2 className="font-display text-2xl text-text-primary mb-1">Criar conta</h2>
      <p className="text-text-muted text-sm mb-8">
        Comece a aprender com histórias em dois idiomas.
      </p>

      <form onSubmit={handleSubmit}>
        <TextField
          id="name"
          label="Nome"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
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
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
        />

        {error && <p className="text-sm text-accent-pt mb-4">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg py-2.5 font-medium text-bg-deep disabled:opacity-60 transition-opacity"
          style={{ backgroundColor: 'var(--color-accent-pt)' }}
        >
          {loading ? 'Criando conta...' : 'Criar minha conta'}
        </button>
      </form>

      <p className="text-text-muted text-sm mt-6">
        Já tem conta?{' '}
        <Link to="/login" className="text-text-primary underline underline-offset-2">
          Entrar
        </Link>
      </p>
    </AuthLayout>
  )
}