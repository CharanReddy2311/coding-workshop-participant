import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProtectedRoute from './ProtectedRoute'

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))

function renderAt(path, minRole) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path={path}
          element={
            <ProtectedRoute minRole={minRole}>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/" element={<div>Home Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseAuth.mockReset()
})

it('shows a spinner while auth is still loading', () => {
  mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: true, hasRole: () => true })
  renderAt('/teams')
  expect(screen.getByRole('progressbar')).toBeInTheDocument()
  expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
})

it('redirects to /login when not authenticated', () => {
  mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: false, hasRole: () => true })
  renderAt('/teams')
  expect(screen.getByText('Login Page')).toBeInTheDocument()
})

it('redirects to / when authenticated but missing the minimum role', () => {
  mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false, hasRole: () => false })
  renderAt('/teams', 'MANAGER')
  expect(screen.getByText('Home Page')).toBeInTheDocument()
})

it('renders children when authenticated and no minRole is required', () => {
  mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false, hasRole: () => true })
  renderAt('/teams')
  expect(screen.getByText('Protected Content')).toBeInTheDocument()
})

it('renders children when authenticated and the minimum role is met', () => {
  mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false, hasRole: () => true })
  renderAt('/teams', 'MANAGER')
  expect(screen.getByText('Protected Content')).toBeInTheDocument()
})
