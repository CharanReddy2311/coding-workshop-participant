import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from './AuthContext'

// vi.mock's factory is hoisted above the rest of the file, so anything it
// references has to be declared inside vi.hoisted() too — a plain `class`/
// `const` below it would still be in the temporal dead zone at that point.
const { MockApiError, mockApi, mockGetAccessToken, mockGetRefreshToken, mockSetTokens, mockClearTokens, mockSetOnAuthFailure } =
  vi.hoisted(() => {
    class MockApiError extends Error {
      constructor(message, { status, code, details } = {}) {
        super(message)
        this.name = 'ApiError'
        this.status = status ?? null
        this.code = code ?? null
        this.details = details || {}
      }
    }

    return {
      MockApiError,
      mockApi: { get: vi.fn(), post: vi.fn() },
      mockGetAccessToken: vi.fn(),
      mockGetRefreshToken: vi.fn(),
      mockSetTokens: vi.fn(),
      mockClearTokens: vi.fn(),
      mockSetOnAuthFailure: vi.fn(),
    }
  })

vi.mock('../services/api', () => ({
  default: {
    get: (...args) => mockApi.get(...args),
    post: (...args) => mockApi.post(...args),
  },
  ApiError: MockApiError,
  getAccessToken: () => mockGetAccessToken(),
  getRefreshToken: () => mockGetRefreshToken(),
  setTokens: (...args) => mockSetTokens(...args),
  clearTokens: (...args) => mockClearTokens(...args),
  setOnAuthFailure: (...args) => mockSetOnAuthFailure(...args),
}))

function TestConsumer() {
  const { user, isAuthenticated, loading, error, login, logout, hasRole } = useAuth()
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="authenticated">{String(isAuthenticated)}</div>
      <div data-testid="user">{user ? user.email : 'none'}</div>
      <div data-testid="error">{error || 'none'}</div>
      <div data-testid="can-manage">{String(hasRole('MANAGER'))}</div>
      <button onClick={() => login('ada@example.com', 'hunter2').catch(() => {})}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

function renderWithProvider() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  mockApi.get.mockReset()
  mockApi.post.mockReset()
  mockGetAccessToken.mockReset().mockReturnValue(null)
  mockGetRefreshToken.mockReset().mockReturnValue(null)
  mockSetTokens.mockReset()
  mockClearTokens.mockReset()
  mockSetOnAuthFailure.mockReset()
})

describe('initial rehydration', () => {
  it('finishes loading with no user when no tokens are stored', async () => {
    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(mockApi.get).not.toHaveBeenCalled()
  })

  it('confirms a stored token via GET /me and adopts the returned user', async () => {
    mockGetAccessToken.mockReturnValue('stored-token')
    mockApi.get.mockResolvedValue({ data: { id: 'u1', email: 'ada@example.com', role: 'ADMIN' } })

    renderWithProvider()

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'))
    expect(mockApi.get).toHaveBeenCalledWith('/auth-service/me')
    expect(screen.getByTestId('user')).toHaveTextContent('ada@example.com')
    expect(JSON.parse(localStorage.getItem('acme_user')).email).toBe('ada@example.com')
  })

  it('logs out when the server confirms the token is genuinely invalid', async () => {
    localStorage.setItem('acme_user', JSON.stringify({ id: 'u1', email: 'stale@example.com', role: 'VIEWER' }))
    mockGetAccessToken.mockReturnValue('expired-token')
    mockApi.get.mockRejectedValue(new MockApiError('Token has expired', { status: 401, code: 'token_expired' }))

    renderWithProvider()

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('false'))
    expect(mockClearTokens).toHaveBeenCalled()
    expect(localStorage.getItem('acme_user')).toBeNull()
  })

  it('keeps the cached session on a network failure instead of logging out', async () => {
    localStorage.setItem('acme_user', JSON.stringify({ id: 'u1', email: 'ada@example.com', role: 'VIEWER' }))
    mockGetAccessToken.mockReturnValue('some-token')
    mockApi.get.mockRejectedValue(new MockApiError('Network error: could not reach the server', { status: 0 }))

    renderWithProvider()

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(mockClearTokens).not.toHaveBeenCalled()
    expect(screen.getByTestId('user')).toHaveTextContent('ada@example.com')
  })
})

describe('login', () => {
  it('stores tokens and adopts the returned user on success', async () => {
    mockApi.post.mockResolvedValue({
      data: {
        access_token: 'new-access',
        refresh_token: 'new-refresh',
        user: { id: 'u1', email: 'ada@example.com', role: 'MANAGER' },
      },
    })

    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await userEvent.click(screen.getByText('Login'))

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'))
    expect(mockApi.post).toHaveBeenCalledWith('/auth-service/login', {
      email: 'ada@example.com',
      password: 'hunter2',
    })
    expect(mockSetTokens).toHaveBeenCalledWith({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      user: { id: 'u1', email: 'ada@example.com', role: 'MANAGER' },
    })
    expect(screen.getByTestId('user')).toHaveTextContent('ada@example.com')
  })

  it('surfaces the backend message on a rejected login', async () => {
    mockApi.post.mockRejectedValue(new MockApiError('Email or password is incorrect', { status: 401 }))

    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await userEvent.click(screen.getByText('Login'))

    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('Email or password is incorrect'))
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
  })

  it('falls back to a generic message for a non-ApiError failure', async () => {
    mockApi.post.mockRejectedValue(new Error('boom'))

    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await userEvent.click(screen.getByText('Login'))

    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('Unable to log in'))
  })
})

describe('logout', () => {
  it('clears tokens, user state, and persisted storage', async () => {
    mockGetAccessToken.mockReturnValue('token')
    mockApi.get.mockResolvedValue({ data: { id: 'u1', email: 'ada@example.com', role: 'ADMIN' } })

    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'))

    await userEvent.click(screen.getByText('Logout'))

    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(mockClearTokens).toHaveBeenCalled()
    expect(localStorage.getItem('acme_user')).toBeNull()
  })
})

describe('hasRole', () => {
  it('ranks roles from the backend ROLES ordering: VIEWER < CONTRIBUTOR < MANAGER < ADMIN', async () => {
    mockGetAccessToken.mockReturnValue('token')
    mockApi.get.mockResolvedValue({ data: { id: 'u1', email: 'ada@example.com', role: 'CONTRIBUTOR' } })

    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'))

    // CONTRIBUTOR does not meet the MANAGER threshold.
    expect(screen.getByTestId('can-manage')).toHaveTextContent('false')
  })

  it('is false for every role when there is no user', async () => {
    renderWithProvider()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('can-manage')).toHaveTextContent('false')
  })
})

describe('useAuth outside a provider', () => {
  it('throws a clear error', () => {
    function Bare() {
      useAuth()
      return null
    }
    // Suppress React's expected error-boundary console noise for this case.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Bare />)).toThrow('useAuth must be used within an AuthProvider')
    spy.mockRestore()
  })
})
