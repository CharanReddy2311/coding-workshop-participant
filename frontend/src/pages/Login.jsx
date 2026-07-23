import { useState } from 'react'
import WorkspacesIcon from '@mui/icons-material/Workspaces'
import { Alert, Box, Button, Card, CircularProgress, Link as MuiLink, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login, isAuthenticated, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Already signed in (e.g. rehydrated from localStorage) — bounce onward
  // rather than showing the form again.
  if (!authLoading && isAuthenticated) {
    return <Navigate to={location.state?.from?.pathname || '/'} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(location.state?.from?.pathname || '/', { replace: true })
    } catch (err) {
      setError(err.message || 'Unable to log in')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Box
      sx={{
        display: 'flex',
        minHeight: '100vh',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card
        elevation={0}
        sx={{
          width: 420,
          maxWidth: '100%',
          p: { xs: 3, sm: 4 },
          boxShadow: '0px 12px 32px rgba(16, 24, 40, 0.12)',
        }}
      >
        <Stack spacing={0.5} sx={{ alignItems: 'center', mb: 3 }}>
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              mb: 1,
            }}
          >
            <WorkspacesIcon />
          </Box>
          <Typography variant="h5" component="h1" fontWeight={700}>
            ACME Project Tracker
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Sign in to continue
          </Typography>
        </Stack>

        <Box component="form" onSubmit={handleSubmit} noValidate>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <TextField
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            fullWidth
            required
            autoFocus
            autoComplete="email"
            margin="normal"
            disabled={submitting}
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            fullWidth
            required
            autoComplete="current-password"
            margin="normal"
            disabled={submitting}
          />

          <Box sx={{ textAlign: 'right', mt: 0.5 }}>
            <MuiLink component={RouterLink} to="/forgot-password" variant="body2" underline="hover">
              Forgot password?
            </MuiLink>
          </Box>

          <Button
            type="submit"
            variant="contained"
            fullWidth
            size="large"
            sx={{ mt: 2 }}
            disabled={submitting || !email || !password}
          >
            {submitting ? <CircularProgress size={24} color="inherit" /> : 'Sign In'}
          </Button>
        </Box>
      </Card>
    </Box>
  )
}
