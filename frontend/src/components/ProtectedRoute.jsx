import { Box, CircularProgress } from '@mui/material'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

/** Gate a route behind login, and optionally a minimum role. */
export default function ProtectedRoute({ children, minRole }) {
  const { isAuthenticated, loading, hasRole } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <Box sx={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (minRole && !hasRole(minRole)) {
    return <Navigate to="/" replace />
  }

  return children
}
