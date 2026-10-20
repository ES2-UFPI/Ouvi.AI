import { apiClient } from '../../shared/api/client'

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  name: string
  email: string
  password: string
}

export async function login(payload: LoginPayload) {
  const { data } = await apiClient.post('/auth/login', payload)
  return data
}

export async function register(payload: RegisterPayload) {
  const { data } = await apiClient.post('/auth/register', payload)
  return data
}