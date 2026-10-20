import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<div>Dashboard (em construção)</div>} />
      <Route path="/login" element={<LoginForm />} />
      <Route path="/cadastro" element={<RegisterForm />} />
    </Routes>
  )
}