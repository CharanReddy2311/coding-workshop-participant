/**
 * Axios client shared by every page. Wraps the ACME backend's response
 * envelope, attaches the JWT, and transparently refreshes it on a 401.
 *
 * Local-dev quirk: bin/proxy-server.js (the LocalStack CORS workaround)
 * rebuilds every request and keeps only accept/content-type/user-agent/host
 * — the Authorization header never survives the hop. backend/_shared/auth.py
 * `_token_from_event` therefore also accepts the token as `?token=...` when
 * the Lambda has IS_LOCAL=true. We send both: the header (so production,
 * where CloudFront talks to the Function URL directly, works normally) and
 * the query param, but only in dev builds (`import.meta.env.DEV`) so a
 * plaintext token never ends up in a production access log.
 */

import axios from 'axios'

const API_BASE_URL = `${import.meta.env.VITE_API_URL || 'http://localhost:3001'}/api`

const ACCESS_TOKEN_KEY = 'acme_access_token'
const REFRESH_TOKEN_KEY = 'acme_refresh_token'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setTokens({ access_token, refresh_token } = {}) {
  if (access_token) localStorage.setItem(ACCESS_TOKEN_KEY, access_token)
  if (refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

/** Normalised shape for every error thrown by this client, success or transport. */
export class ApiError extends Error {
  constructor(message, { status, code, details } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status ?? null
    this.code = code ?? null
    this.details = details || {}
  }
}

function toApiError(error) {
  const res = error.response
  if (!res) {
    return new ApiError('Network error: could not reach the server', { status: 0 })
  }
  const body = res.data?.error
  return new ApiError(body?.message || 'An unexpected error occurred', {
    status: res.status,
    code: body?.code,
    details: body?.details,
  })
}

// Set by AuthContext so a failed refresh can log the user out, without this
// module importing the context (which imports this module) back.
let onAuthFailure = () => {}
export function setOnAuthFailure(handler) {
  onAuthFailure = handler
}

const api = axios.create({ baseURL: API_BASE_URL })

function attachToken(config, token) {
  config.headers = config.headers || {}
  config.headers.Authorization = `Bearer ${token}`
  if (import.meta.env.DEV) {
    config.params = { ...config.params, token }
  }
  return config
}

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  return token ? attachToken(config, token) : config
})

// Every 401 outside login/refresh triggers exactly one refresh attempt,
// shared across concurrent requests so a burst of calls doesn't fire the
// refresh endpoint more than once.
let refreshPromise = null

async function refreshAccessToken() {
  const refresh_token = getRefreshToken()
  if (!refresh_token) {
    throw new ApiError('No refresh token available', { status: 401, code: 'no_refresh_token' })
  }
  // Raw axios, not `api`: going through the instance would re-enter this
  // same response interceptor.
  const res = await axios.post(`${API_BASE_URL}/auth-service/refresh`, { refresh_token })
  const data = res.data?.data
  setTokens(data)
  return data.access_token
}

api.interceptors.response.use(
  // Unwrap the backend's { data, meta } envelope so callers work with plain
  // values; list endpoints keep their pagination info at response.meta.
  (response) => {
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      response.meta = response.data.meta
      response.data = response.data.data
    }
    return response
  },
  async (error) => {
    const { config, response } = error

    if (!response) {
      return Promise.reject(toApiError(error))
    }

    const url = config?.url || ''
    const isAuthRoute = url.includes('/auth-service/login') || url.includes('/auth-service/refresh')

    if (response.status === 401 && !isAuthRoute && config && !config._retried) {
      config._retried = true
      try {
        refreshPromise = refreshPromise || refreshAccessToken()
        const token = await refreshPromise
        refreshPromise = null
        return api(attachToken(config, token))
      } catch (refreshError) {
        refreshPromise = null
        clearTokens()
        onAuthFailure()
        return Promise.reject(toApiError(refreshError))
      }
    }

    return Promise.reject(toApiError(error))
  },
)

export default api
