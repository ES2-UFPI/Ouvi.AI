import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'
import { ProtectedRoute } from '../shared/components/ProtectedRoute'
import { AudioFilterPanel } from '../features/filters/components/AudioFilterPanel'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginForm />} />
      <Route path="/cadastro" element={<RegisterForm />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<div>Dashboard (em construção)
          <Route path="/filter" element={<div className="p-8 max-w-md"><AudioFilterPanel /></div>} />

        </div>} />
      </Route>
    </Routes>
  )
}
