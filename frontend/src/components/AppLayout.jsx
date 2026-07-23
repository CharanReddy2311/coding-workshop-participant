import { AppBar, Button, Chip, Toolbar, Typography } from '@mui/material'
import { Link } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

const NAV_LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/teams', label: 'Teams' },
  { to: '/projects', label: 'Projects' },
  { to: '/deliverables', label: 'Deliverables' },
  { to: '/allocations', label: 'Allocations' },
]

/** Shared top nav bar for every authenticated page. */
export default function AppLayout({ children }) {
  const { user, logout } = useAuth()

  return (
    <>
      <AppBar position="static">
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            ACME Project Tracker
          </Typography>
          {NAV_LINKS.map((link) => (
            <Button key={link.to} color="inherit" component={Link} to={link.to}>
              {link.label}
            </Button>
          ))}
          <Chip label={user.role} color="secondary" size="small" />
          <Typography variant="body2">{user.full_name}</Typography>
          <Button color="inherit" onClick={logout}>
            Log Out
          </Button>
        </Toolbar>
      </AppBar>
      {children}
    </>
  )
}
