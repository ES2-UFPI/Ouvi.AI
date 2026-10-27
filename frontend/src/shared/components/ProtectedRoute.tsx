import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../features/auth/store'

export function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()

  if (!token) {
  return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}