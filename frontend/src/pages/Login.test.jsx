import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import Login from './Login'

const { mockUseAuth, mockLogin, mockNavigate } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockLogin: vi.fn(),
  mockNavigate: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderLogin(initialEntries = ['/login']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<div>Home Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseAuth.mockReset().mockReturnValue({ login: mockLogin, isAuthenticated: false, loading: false })
  mockLogin.mockReset()
  mockNavigate.mockReset()
})

it('renders the sign-in form with submit disabled until both fields are filled', () => {
  renderLogin()
  expect(screen.getByRole('button', { name: 'Sign In' })).toBeDisabled()
})

it('does not render a demo mode or self-service registration option', () => {
  renderLogin()
  expect(screen.queryByText(/preview as a role/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/preview dashboard/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/create one/i)).not.toBeInTheDocument()
})

it('redirects away immediately when already authenticated', () => {
  mockUseAuth.mockReturnValue({ login: mockLogin, isAuthenticated: true, loading: false })
  renderLogin()
  expect(screen.getByText('Home Page')).toBeInTheDocument()
})

it('submits credentials and navigates home on success', async () => {
  mockLogin.mockResolvedValue(undefined)
  renderLogin()

  await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'hunter2')
  await userEvent.click(screen.getByRole('button', { name: 'Sign In' }))

  expect(mockLogin).toHaveBeenCalledWith('ada@example.com', 'hunter2')
  expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
})

it('shows the error message when login fails', async () => {
  mockLogin.mockRejectedValue(new Error('Email or password is incorrect'))
  renderLogin()

  await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Sign In' }))

  expect(await screen.findByText('Email or password is incorrect')).toBeInTheDocument()
  expect(mockNavigate).not.toHaveBeenCalled()
})

it('falls back to a generic message when the error has no message', async () => {
  mockLogin.mockRejectedValue({})
  renderLogin()

  await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
  await userEvent.type(screen.getByLabelText(/password/i), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Sign In' }))

  expect(await screen.findByText('Unable to log in')).toBeInTheDocument()
})
