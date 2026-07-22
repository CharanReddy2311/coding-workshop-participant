import { Box, Container, Paper, Typography } from '@mui/material'

import AppLayout from '../components/AppLayout'
import { useAuth } from '../context/AuthContext'

// Placeholder home screen — proves the login/logout loop end-to-end.
export default function Dashboard() {
  const { user } = useAuth()

  return (
    <AppLayout>
      <Container sx={{ mt: 4 }}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h5" gutterBottom>
            Welcome, {user.full_name}
          </Typography>
          <Box sx={{ color: 'text.secondary' }}>
            Logged in as {user.email} ({user.role}).
          </Box>
        </Paper>
      </Container>
    </AppLayout>
  )
}
