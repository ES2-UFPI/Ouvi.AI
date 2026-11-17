import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ProtectedRoute } from './ProtectedRoute'
import { useAuthStore } from '../../features/auth/store'

function TelaDeLogin() {
  const { state } = useLocation()
  return <div>Login (veio de {(state as { from?: string } | null)?.from ?? 'lugar nenhum'})</div>
}

function renderRota(inicial: string) {
  return render(
    <MemoryRouter initialEntries={[inicial]}>
      <Routes>
        <Route path="/login" element={<TelaDeLogin />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/filter" element={<div>Conteúdo protegido</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, refreshToken: null })
})

describe('ProtectedRoute', () => {
  it('sem sessão, redireciona para o login guardando a página pedida', () => {
    renderRota('/filter')
    expect(screen.getByText('Login (veio de /filter)')).toBeInTheDocument()
    expect(screen.queryByText('Conteúdo protegido')).not.toBeInTheDocument()
  })

  it('com sessão, mostra o conteúdo', () => {
    useAuthStore.getState().setTokens('abc', 'ref')
    renderRota('/filter')
    expect(screen.getByText('Conteúdo protegido')).toBeInTheDocument()
  })

  it('ao encerrar a sessão, a rota volta a ficar protegida', () => {
    useAuthStore.getState().setTokens('abc', 'ref')
    useAuthStore.getState().logout()
    renderRota('/filter')
    expect(screen.queryByText('Conteúdo protegido')).not.toBeInTheDocument()
  })
})
