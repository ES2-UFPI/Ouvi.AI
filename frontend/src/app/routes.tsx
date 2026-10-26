import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'
import { ProtectedRoute } from '../shared/components/ProtectedRoute'
import { AudioFilterPanel } from '../features/filters/components/AudioFilterPanel'
import { PlayerPage } from '../features/player/components/PlayerPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginForm />} />
      <Route path="/cadastro" element={<RegisterForm />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<div>Dashboard (em construção)</div>} />

        <Route
          path="/filter"
          element={
            <div className="p-8 max-w-md">
              <AudioFilterPanel />
            </div>
          }
        />

        <Route path="/player/:materialId" element={<PlayerPage />} />
      </Route>
    </Routes>
  )
}