import { useState } from 'react'
import MenuIcon from '@mui/icons-material/Menu'
import {
  AppBar,
  Avatar,
  Box,
  Button,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Stack,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { Link, useLocation } from 'react-router-dom'

import { useAuth } from '../context/AuthContext'

const NAV_LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/teams', label: 'Teams' },
  { to: '/projects', label: 'Projects' },
  { to: '/deliverables', label: 'Deliverables' },
  { to: '/allocations', label: 'Allocations' },
]

function initials(fullName) {
  return fullName
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

/** Shared top nav bar for every authenticated page. */
export default function AppLayout({ children }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const theme = useTheme()
  // 'lg' (not 'md') — the title plus all five nav links plus the role chip,
  // avatar/name, and Log Out button need close to 1150px to lay out in one
  // row without overflowing the Toolbar. Switching to the hamburger menu
  // earlier, while there's still headroom, is what actually prevents that
  // overflow rather than just reacting to it.
  const isMobile = useMediaQuery(theme.breakpoints.down('lg'))
  const [menuAnchor, setMenuAnchor] = useState(null)

  return (
    <>
      <AppBar position="static" elevation={0}>
        <Toolbar sx={{ gap: 1.5 }}>
          <Typography
            variant="h6"
            noWrap
            sx={{ flexGrow: 1, flexShrink: 1, minWidth: 0, fontWeight: 700 }}
          >
            ACME Project Tracker
          </Typography>

          {isMobile ? (
            <>
              <IconButton
                color="inherit"
                aria-label="Open navigation menu"
                onClick={(event) => setMenuAnchor(event.currentTarget)}
              >
                <MenuIcon />
              </IconButton>
              <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
                {NAV_LINKS.map((link) => (
                  <MenuItem
                    key={link.to}
                    component={Link}
                    to={link.to}
                    selected={location.pathname === link.to}
                    onClick={() => setMenuAnchor(null)}
                  >
                    {link.label}
                  </MenuItem>
                ))}
              </Menu>
            </>
          ) : (
            <Stack direction="row" spacing={0.5}>
              {NAV_LINKS.map((link) => (
                <Button
                  key={link.to}
                  color="inherit"
                  component={Link}
                  to={link.to}
                  sx={{
                    fontWeight: location.pathname === link.to ? 700 : 500,
                    bgcolor: location.pathname === link.to ? 'rgba(255,255,255,0.14)' : 'transparent',
                  }}
                >
                  {link.label}
                </Button>
              ))}
            </Stack>
          )}

          <Chip label={user.role} color="secondary" size="small" sx={{ ml: 1 }} />
          {!isMobile && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', ml: 1 }}>
              <Avatar sx={{ width: 30, height: 30, fontSize: 13, bgcolor: 'primary.light' }}>
                {initials(user.full_name)}
              </Avatar>
              <Typography variant="body2">{user.full_name}</Typography>
            </Stack>
          )}
          <Button color="inherit" onClick={logout} sx={{ ml: 1 }}>
            Log Out
          </Button>
        </Toolbar>
      </AppBar>
      {children}
    </>
  )
}
