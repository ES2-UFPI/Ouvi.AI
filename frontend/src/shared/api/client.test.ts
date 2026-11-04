import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../features/auth/store'
import { apiClient } from './client'

type Handler = (config: InternalAxiosRequestConfig) => { status: number; data?: unknown }

/** Troca o adaptador HTTP do cliente por uma função, para testar os interceptors sem rede. */
function simularServidor(handler: Handler) {
  // Guarda o valor do header NO MOMENTO da chamada: na repetição o interceptor reutiliza (e altera)
  // o mesmo objeto de configuração, então guardar o objeto esconderia o primeiro valor.
  const chamadas: unknown[] = []
  apiClient.defaults.adapter = async (config) => {
    chamadas.push(config.headers.Authorization)
    const { status, data = {} } = handler(config)
    const response = { status, data, statusText: '', headers: {}, config }
    if (status >= 400) {
      throw new AxiosError('falhou', 'ERR_BAD_REQUEST', config, null, response)
    }
    return response
  }
  return chamadas
}

const authorization = (config: InternalAxiosRequestConfig) => config.headers.Authorization

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, refreshToken: null })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('apiClient: token nas requisições', () => {
  it('envia o access token no header Authorization', async () => {
    useAuthStore.getState().setTokens('abc', 'ref')
    const chamadas = simularServidor(() => ({ status: 200 }))
    await apiClient.get('/stories')
    expect(chamadas[0]).toBe('Bearer abc')
  })

  it('não envia o header quando não há sessão', async () => {
    const chamadas = simularServidor(() => ({ status: 200 }))
    await apiClient.get('/stories')
    expect(chamadas[0]).toBeUndefined()
  })
})

describe('apiClient: renovação automática do token', () => {
  it('no 401 renova o token e repete a requisição uma vez', async () => {
    useAuthStore.getState().setTokens('velho', 'ref-1')
    const renovar = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: 'novo', refresh_token: 'ref-2' },
    })
    const chamadas = simularServidor((config) =>
      authorization(config) === 'Bearer novo' ? { status: 200, data: { ok: true } } : { status: 401 },
    )

    const resposta = await apiClient.get('/stories')

    expect(resposta.data).toEqual({ ok: true })
    expect(renovar).toHaveBeenCalledTimes(1)
    expect(renovar.mock.calls[0][1]).toEqual({ refresh_token: 'ref-1' })
    expect(chamadas).toEqual(['Bearer velho', 'Bearer novo'])
    expect(useAuthStore.getState()).toMatchObject({ token: 'novo', refreshToken: 'ref-2' })
  })

  it('várias requisições com 401 ao mesmo tempo fazem uma única renovação', async () => {
    useAuthStore.getState().setTokens('velho', 'ref-1')
    const renovar = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access_token: 'novo', refresh_token: 'ref-2' },
    })
    simularServidor((config) => (authorization(config) === 'Bearer novo' ? { status: 200 } : { status: 401 }))

    await Promise.all([apiClient.get('/stories'), apiClient.get('/filters'), apiClient.get('/users/me')])

    expect(renovar).toHaveBeenCalledTimes(1)
  })

  it('se a renovação falha, encerra a sessão e devolve o erro', async () => {
    useAuthStore.getState().setTokens('velho', 'ref-1')
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh expirado'))
    simularServidor(() => ({ status: 401 }))

    await expect(apiClient.get('/stories')).rejects.toBeTruthy()
    expect(useAuthStore.getState()).toMatchObject({ token: null, refreshToken: null })
  })

  it('sem refresh token, encerra a sessão em vez de tentar renovar', async () => {
    useAuthStore.setState({ token: 'velho', refreshToken: null })
    const renovar = vi.spyOn(axios, 'post')
    simularServidor(() => ({ status: 401 }))

    await expect(apiClient.get('/stories')).rejects.toBeTruthy()
    expect(renovar).not.toHaveBeenCalled()
    expect(useAuthStore.getState().token).toBeNull()
  })

  it('um 401 no login é erro de credencial: não renova nem encerra a sessão', async () => {
    useAuthStore.getState().setTokens('abc', 'ref')
    const renovar = vi.spyOn(axios, 'post')
    simularServidor(() => ({ status: 401 }))

    await expect(apiClient.post('/auth/login', {})).rejects.toBeTruthy()
    expect(renovar).not.toHaveBeenCalled()
    expect(useAuthStore.getState().token).toBe('abc')
  })

  it('outros erros (como 404) passam direto, sem renovar', async () => {
    useAuthStore.getState().setTokens('abc', 'ref')
    const renovar = vi.spyOn(axios, 'post')
    simularServidor(() => ({ status: 404 }))

    await expect(apiClient.get('/stories/999')).rejects.toMatchObject({ response: { status: 404 } })
    expect(renovar).not.toHaveBeenCalled()
    expect(useAuthStore.getState().token).toBe('abc')
  })
})
