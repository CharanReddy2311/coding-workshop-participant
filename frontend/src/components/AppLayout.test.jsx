import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import AppLayout from './AppLayout'

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))

beforeEach(() => {
  mockUseAuth.mockReset()
})

it('renders the nav links, current user, role chip, and children', () => {
  mockUseAuth.mockReturnValue({
    user: { full_name: 'Ada Lovelace', role: 'ADMIN' },
    logout: vi.fn(),
  })

  render(
    <MemoryRouter>
      <AppLayout>
        <div>Page Content</div>
      </AppLayout>
    </MemoryRouter>,
  )

  ;['Dashboard', 'Teams', 'Projects', 'Deliverables', 'Allocations'].forEach((label) => {
    expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
  })
  expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByText('ADMIN')).toBeInTheDocument()
  expect(screen.getByText('Page Content')).toBeInTheDocument()
})

it('calls logout when Log Out is clicked', async () => {
  const logout = vi.fn()
  mockUseAuth.mockReturnValue({ user: { full_name: 'Ada Lovelace', role: 'ADMIN' }, logout })

  render(
    <MemoryRouter>
      <AppLayout>
        <div>Page Content</div>
      </AppLayout>
    </MemoryRouter>,
  )

  await userEvent.click(screen.getByRole('button', { name: 'Log Out' }))
  expect(logout).toHaveBeenCalled()
})
