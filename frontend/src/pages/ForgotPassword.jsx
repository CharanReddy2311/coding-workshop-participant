import { useState } from 'react'
import WorkspacesIcon from '@mui/icons-material/Workspaces'
import { Alert, Box, Button, Card, Link as MuiLink, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'

/**
 * UX-only preview of a password-reset flow. backend/auth-service has no
 * reset-token endpoint yet — submitting simulates the request rather than
 * sending a real email. Wire this up to a real
 * POST /auth-service/forgot-password once it exists.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

  function handleSubmit(event) {
    event.preventDefault()
    setSubmitted(true)
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
        sx={{ width: 420, maxWidth: '100%', p: { xs: 3, sm: 4 }, boxShadow: '0px 12px 32px rgba(16, 24, 40, 0.12)' }}
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
            Reset your password
          </Typography>
          <Typography variant="body2" color="text.secondary" align="center">
            This preview shows the intended reset flow.
          </Typography>
        </Stack>

        <Alert severity="info" sx={{ mb: 3 }}>
          Password reset isn&apos;t wired up to the backend yet. This form previews the intended flow only; no email
          is sent.
        </Alert>

        {submitted ? (
          <Stack spacing={2} sx={{ alignItems: 'center', py: 2 }}>
            <Alert severity="success" sx={{ width: '100%' }}>
              If an account exists for {email || 'that address'}, a reset link would be sent next.
            </Alert>
            <Button component={RouterLink} to="/login" variant="contained">
              Back to Sign In
            </Button>
          </Stack>
        ) : (
          <Box component="form" onSubmit={handleSubmit} noValidate>
            <TextField
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              fullWidth
              required
              autoFocus
              margin="normal"
            />
            <Button type="submit" variant="contained" fullWidth size="large" sx={{ mt: 2 }} disabled={!email}>
              Send Reset Link
            </Button>
            <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 2 }}>
              <MuiLink component={RouterLink} to="/login" underline="hover">
                Back to Sign In
              </MuiLink>
            </Typography>
          </Box>
        )}
      </Card>
    </Box>
  )
}
