import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'
import { ProtectedRoute } from '../shared/components/ProtectedRoute'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginForm />} />
      <Route path="/cadastro" element={<RegisterForm />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<div>Dashboard (em construção)</div>} />
      </Route>
    </Routes>
  )
}