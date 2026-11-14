import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RegisterForm } from './RegisterForm'
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

function renderCadastro() {
  return render(
    <MemoryRouter initialEntries={['/cadastro']}>
      <Routes>
        <Route path="/cadastro" element={<RegisterForm />} />
        <Route path="/login" element={<div>Tela de login</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function preencherEEnviar() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Nome'), 'Ana')
  await user.type(screen.getByLabelText('E-mail'), 'ana@teste.com')
  await user.type(screen.getByLabelText('Senha'), 'Senha1234')
  await user.click(screen.getByRole('button', { name: 'Criar minha conta' }))
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('RegisterForm', () => {
  it('mostra os campos e o link para entrar', () => {
    renderCadastro()
    expect(screen.getByLabelText('Nome')).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail')).toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Entrar' })).toHaveAttribute('href', '/login')
  })

  it('a senha exige no mínimo 8 caracteres já no campo', () => {
    renderCadastro()
    expect(screen.getByLabelText('Senha')).toHaveAttribute('minLength', '8')
  })

  it('cadastro com sucesso envia os dados e leva para o login', async () => {
    vi.mocked(authApi.register).mockResolvedValue({})
    renderCadastro()
    await preencherEEnviar()

    expect(await screen.findByText('Tela de login')).toBeInTheDocument()
    expect(authApi.register).toHaveBeenCalledWith({ name: 'Ana', email: 'ana@teste.com', password: 'Senha1234' })
  })

  it('e-mail já cadastrado (409) mostra a mensagem específica', async () => {
    vi.mocked(authApi.register).mockRejectedValue(erroHttp(409))
    renderCadastro()
    await preencherEEnviar()
    expect(await screen.findByText(/Este e-mail já está cadastrado/)).toBeInTheDocument()
  })

  it('dados inválidos (422) explicam o que conferir', async () => {
    vi.mocked(authApi.register).mockRejectedValue(erroHttp(422))
    renderCadastro()
    await preencherEEnviar()
    expect(await screen.findByText(/senha com no mínimo 8 caracteres/)).toBeInTheDocument()
  })

  it('qualquer outro erro mostra uma mensagem genérica', async () => {
    vi.mocked(authApi.register).mockRejectedValue(new Error('Network Error'))
    renderCadastro()
    await preencherEEnviar()
    expect(await screen.findByText(/Não foi possível criar sua conta agora/)).toBeInTheDocument()
  })

  it('o erro some quando o usuário tenta de novo', async () => {
    vi.mocked(authApi.register).mockRejectedValueOnce(erroHttp(409)).mockResolvedValueOnce({})
    renderCadastro()
    await preencherEEnviar()
    await screen.findByText(/Este e-mail já está cadastrado/)

    await userEvent.setup().click(screen.getByRole('button', { name: 'Criar minha conta' }))
    expect(await screen.findByText('Tela de login')).toBeInTheDocument()
  })
})
