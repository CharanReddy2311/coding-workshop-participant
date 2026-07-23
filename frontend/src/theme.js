import { createTheme } from '@mui/material'

// Corporate blue/grey palette — used across nav, primary actions, and chips.
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1e3a5f',
      light: '#3f5c85',
      dark: '#122842',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#2f9e8f',
    },
    background: {
      default: '#f4f6f9',
      paper: '#ffffff',
    },
    text: {
      primary: '#1a2233',
      secondary: '#5b6b82',
    },
    divider: '#e2e8f0',
    success: { main: '#2e9e6b' },
    warning: { main: '#c98a1e' },
    error: { main: '#c0392b' },
    info: { main: '#2f6f9e' },
  },
  shape: {
    borderRadius: 12,
  },
  typography: {
    fontFamily: [
      'Inter',
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      'Helvetica',
      'Arial',
      'sans-serif',
    ].join(','),
    h4: { fontWeight: 700, letterSpacing: -0.5 },
    h5: { fontWeight: 700, letterSpacing: -0.3 },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, color: '#5b6b82' },
    button: { fontWeight: 600, textTransform: 'none' },
  },
  shadows: [
    'none',
    '0px 1px 2px rgba(16, 24, 40, 0.06)',
    '0px 1px 3px rgba(16, 24, 40, 0.08)',
    '0px 2px 6px rgba(16, 24, 40, 0.08)',
    '0px 4px 10px rgba(16, 24, 40, 0.08)',
    ...Array(20).fill('0px 8px 24px rgba(16, 24, 40, 0.10)'),
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // Backstop, not the fix: if any element ever overflows its
        // container width (a too-wide toolbar, an unwrapped table), this
        // keeps the page itself from picking up a horizontal scrollbar —
        // which otherwise leaves every other route mis-scrolled too, since
        // SPA navigation doesn't reset scroll position on its own.
        html: { overflowX: 'hidden' },
        body: { backgroundColor: '#f4f6f9', overflowX: 'hidden' },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        rounded: { borderRadius: 12 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          border: '1px solid #e2e8f0',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 10, paddingLeft: 16, paddingRight: 16 },
      },
      defaultProps: {
        disableElevation: true,
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#1e3a5f',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontWeight: 700, color: '#5b6b82', backgroundColor: '#f8fafc' },
      },
    },
  },
})

export default theme
