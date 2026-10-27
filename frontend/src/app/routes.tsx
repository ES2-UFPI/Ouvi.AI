import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'
import { PageLayout } from '../shared/components/PageLayout'
import { ProtectedRoute } from '../shared/components/ProtectedRoute'
import { AudioFilterPanel } from '../features/filters/components/AudioFilterPanel'
import { PlayerPage } from '../features/player/components/PlayerPage'
import { DevNav } from '../test/DevNav'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/dev" element={<DevNav />} />

      <Route path="/login" element={<LoginForm />} />
      <Route path="/cadastro" element={<RegisterForm />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<div>Dashboard (em construção)</div>} />

        <Route
          path="/filter"
          element={
            <PageLayout>
              <AudioFilterPanel />
            </PageLayout>
          }
        />

        <Route path="/player/:storyId" element={<PlayerPage />} />
      </Route>
    </Routes>
  )
}