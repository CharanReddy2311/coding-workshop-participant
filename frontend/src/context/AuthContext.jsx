import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import api, { ApiError, clearTokens, getAccessToken, getRefreshToken, setOnAuthFailure, setTokens } from '../services/api'

const USER_KEY = 'acme_user'

// Mirrors backend/_shared/auth.py ROLES — least to most privileged.
const ROLE_RANK = { VIEWER: 0, CONTRIBUTOR: 1, MANAGER: 2, ADMIN: 3 }

const AuthContext = createContext(null)

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function persistUser(user) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadStoredUser)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const logout = useCallback(() => {
    clearTokens()
    persistUser(null)
    setUser(null)
  }, [])

  useEffect(() => {
    setOnAuthFailure(logout)
  }, [logout])

  // A cached user from localStorage may be stale (role changed, account
  // deactivated) or the access token may have expired while the tab was
  // closed, so confirm against GET /me before trusting it. api.js already
  // retries once via the refresh token on a 401, so this only logs out if
  // both tokens are dead.
  useEffect(() => {
    let cancelled = false

    async function rehydrate() {
      if (!getAccessToken() && !getRefreshToken()) {
        setLoading(false)
        return
      }
      try {
        const res = await api.get('/auth-service/me')
        if (!cancelled) {
          setUser(res.data)
          persistUser(res.data)
        }
      } catch (err) {
        // Only a confirmed rejection from the server (bad/expired tokens,
        // account deactivated) should sign the user out. A transport
        // failure (status 0 — server unreachable, offline, restarting)
        // says nothing about whether the tokens are still valid, so leave
        // the cached session alone and let the next request retry.
        if (!cancelled && err instanceof ApiError && err.status && err.status !== 0) {
          logout()
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    rehydrate()
    return () => {
      cancelled = true
    }
  }, [logout])

  const login = useCallback(async (email, password) => {
    setError(null)
    try {
      const res = await api.post('/auth-service/login', { email, password })
      setTokens(res.data)
      setUser(res.data.user)
      persistUser(res.data.user)
      return res.data.user
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to log in')
      throw err
    }
  }, [])

  const hasRole = useCallback(
    (minimumRole) => !!user && ROLE_RANK[user.role] >= ROLE_RANK[minimumRole],
    [user],
  )

  const value = useMemo(
    () => ({ user, isAuthenticated: !!user, loading, error, login, logout, hasRole }),
    [user, loading, error, login, logout, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components -- hook belongs with its provider
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
