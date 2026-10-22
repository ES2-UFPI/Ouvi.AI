import axios, { type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '../../features/auth/store'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const apiClient = axios.create({ baseURL })

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Rotas de autenticação nunca tentam renovar o token: um 401 nelas é erro de credencial
const isAuthRoute = (url?: string) => url?.startsWith('/auth/') ?? false

// Várias requisições podem receber 401 ao mesmo tempo: todas esperam a mesma renovação
let refreshing: Promise<string> | null = null

function renewAccessToken(): Promise<string> {
  const { refreshToken, setTokens } = useAuthStore.getState()
  if (!refreshToken) return Promise.reject(new Error('sem refresh token'))

  refreshing ??= axios
    .post(`${baseURL}/auth/refresh`, { refresh_token: refreshToken })
    .then(({ data }) => {
      setTokens(data.access_token, data.refresh_token)
      return data.access_token as string
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as RetriableConfig | undefined

    if (error.response?.status !== 401 || !original || isAuthRoute(original.url)) {
      return Promise.reject(error)
    }

    // Access token expirou: renova uma vez e repete a requisição original
    if (!original._retry) {
      original._retry = true
      try {
        // Se outra requisição já renovou o token enquanto esta esperava a resposta, só repete com o novo
        const current = useAuthStore.getState().token
        const alreadyRenewed = current && original.headers.Authorization !== `Bearer ${current}`
        const newToken = alreadyRenewed ? current : await renewAccessToken()
        original.headers.Authorization = `Bearer ${newToken}`
        return apiClient(original)
      } catch {
        // renovação falhou: a sessão acabou de verdade
      }
    }

    useAuthStore.getState().logout()
    return Promise.reject(error)
  },
)
