import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LoginForm } from './LoginForm'
import { useAuthStore } from '../store'
import * as authApi from '../api'

vi.mock('../api')

function erroHttp(status: number) {
  return new AxiosError('falhou', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    data: {},
    statusText: '',
    headers: {},
    config: {} as never,
  })
}

function renderLogin(from?: string) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/login', state: from ? { from } : undefined }]}>
      <Routes>
        <Route path="/login" element={<LoginForm />} />
        <Route path="/cadastro" element={<div>Tela de cadastro</div>} />
        <Route path="/" element={<div>Tela inicial</div>} />
        <Route path="/filter" element={<div>Tela do filtro</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function preencherEEnviar(email = 'ana@teste.com', senha = 'Senha1234') {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('E-mail'), email)
  await user.type(screen.getByLabelText('Senha'), senha)
  await user.click(screen.getByRole('button', { name: 'Entrar' }))
}

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  useAuthStore.setState({ token: null, refreshToken: null })
})

describe('LoginForm', () => {
  it('mostra os campos e o link para criar conta', () => {
    renderLogin()
    expect(screen.getByLabelText('E-mail')).toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Criar conta' })).toHaveAttribute('href', '/cadastro')
  })

  it('com credenciais corretas guarda os tokens e vai para a tela inicial', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'a', refresh_token: 'r' })
    renderLogin()
    await preencherEEnviar()

    expect(await screen.findByText('Tela inicial')).toBeInTheDocument()
    expect(authApi.login).toHaveBeenCalledWith({ email: 'ana@teste.com', password: 'Senha1234' })
    expect(useAuthStore.getState()).toMatchObject({ token: 'a', refreshToken: 'r' })
  })

  it('volta para a página que o usuário tentou abrir antes de entrar', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'a', refresh_token: 'r' })
    renderLogin('/filter')
    await preencherEEnviar()
    expect(await screen.findByText('Tela do filtro')).toBeInTheDocument()
  })

  it('credenciais erradas (401) mostram a mensagem de e-mail ou senha incorretos', async () => {
    vi.mocked(authApi.login).mockRejectedValue(erroHttp(401))
    renderLogin()
    await preencherEEnviar()

    expect(await screen.findByText('E-mail ou senha incorretos.')).toBeInTheDocument()
    expect(useAuthStore.getState().token).toBeNull()
  })

  it('outro erro (API fora do ar) mostra uma mensagem diferente da de credencial', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('Network Error'))
    renderLogin()
    await preencherEEnviar()
    expect(await screen.findByText(/Não foi possível entrar agora/)).toBeInTheDocument()
  })

  it('desativa o botão enquanto espera a resposta', async () => {
    vi.mocked(authApi.login).mockReturnValue(new Promise(() => {}))
    renderLogin()
    await preencherEEnviar()
    expect(await screen.findByRole('button', { name: 'Entrando...' })).toBeDisabled()
  })
})
