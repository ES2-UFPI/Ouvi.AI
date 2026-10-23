import { Routes, Route } from 'react-router-dom'
import { LoginForm } from '../features/auth/components/LoginForm'
import { RegisterForm } from '../features/auth/components/RegisterForm'
import { ProtectedRoute } from '../shared/components/ProtectedRoute'
import { AudioFilterPanel } from '../features/filters/components/AudioFilterPanel'
import { AudioPlayer } from '../features/player/components/AudioPlayer'

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

        <Route
          path="/player"
          element={
            <div className="p-8 max-w-md">
              <AudioPlayer
                src="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
                title="Teste do player"
              />
            </div>
          }
        />
      </Route>
    </Routes>
  )
}