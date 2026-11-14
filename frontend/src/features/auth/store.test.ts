import { beforeEach, describe, expect, it } from 'vitest'
import { useAuthStore } from './store'

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, refreshToken: null })
})

describe('useAuthStore', () => {
  it('começa sem sessão', () => {
    const { token, refreshToken } = useAuthStore.getState()
    expect(token).toBeNull()
    expect(refreshToken).toBeNull()
  })

  it('guarda os dois tokens', () => {
    useAuthStore.getState().setTokens('acesso', 'renovacao')
    expect(useAuthStore.getState()).toMatchObject({ token: 'acesso', refreshToken: 'renovacao' })
  })

  it('logout apaga os dois tokens', () => {
    useAuthStore.getState().setTokens('acesso', 'renovacao')
    useAuthStore.getState().logout()
    expect(useAuthStore.getState()).toMatchObject({ token: null, refreshToken: null })
  })

  it('persiste a sessão no localStorage, para sobreviver a um recarregamento', () => {
    useAuthStore.getState().setTokens('acesso', 'renovacao')
    const salvo = JSON.parse(localStorage.getItem('ouveai-auth') ?? '{}')
    expect(salvo.state).toMatchObject({ token: 'acesso', refreshToken: 'renovacao' })
  })

  it('logout também limpa o que foi persistido', () => {
    useAuthStore.getState().setTokens('acesso', 'renovacao')
    useAuthStore.getState().logout()
    const salvo = JSON.parse(localStorage.getItem('ouveai-auth') ?? '{}')
    expect(salvo.state.token).toBeNull()
  })
})
