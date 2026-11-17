import { apiClient } from '../../shared/api/client'

export interface CurrentUser {
  id: number
  name: string
  email: string
}

// Dados do usuário logado (GET /users/me)
export async function getMe() {
  const { data } = await apiClient.get<CurrentUser>('/users/me')
  return data
}
