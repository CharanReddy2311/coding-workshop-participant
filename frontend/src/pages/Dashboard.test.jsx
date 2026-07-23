import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))

beforeEach(() => {
  mockUseAuth.mockReset()
})

it('greets the logged-in user with their name, email, and role', () => {
  mockUseAuth.mockReturnValue({
    user: { full_name: 'Ada Lovelace', email: 'ada@example.com', role: 'MANAGER' },
    logout: vi.fn(),
  })

  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )

  expect(screen.getByText('Welcome, Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByText('Logged in as ada@example.com (MANAGER).')).toBeInTheDocument()
})
