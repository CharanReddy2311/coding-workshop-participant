import { beforeEach, describe, expect, it, vi } from 'vitest'

// axios.create() registers our interceptors at module-import time, so the
// only way to unit-test that logic without a real network call is to mock
// axios.create() to return a fake instance that just records the callbacks
// it's handed — then invoke those callbacks directly.
const interceptors = { request: [], response: [] }

vi.mock('axios', () => {
  // A real axios instance is a callable function with extra properties
  // (interceptors, .get, .post, ...) attached — api(config) in the retry
  // path calls the instance directly, so the mock has to be callable too,
  // not just an object.
  const instance = vi.fn(() => Promise.resolve({ data: {} }))
  instance.interceptors = {
    request: { use: vi.fn((onFulfilled) => interceptors.request.push(onFulfilled)) },
    response: {
      use: vi.fn((onFulfilled, onRejected) => interceptors.response.push({ onFulfilled, onRejected })),
    },
  }
  return {
    default: {
      create: vi.fn(() => instance),
      post: vi.fn(),
    },
  }
})

const axios = (await import('axios')).default
const {
  ApiError,
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  setOnAuthFailure,
} = await import('./api')

const requestInterceptor = interceptors.request[0]
const { onFulfilled: responseSuccess, onRejected: responseError } = interceptors.response[0]

beforeEach(() => {
  localStorage.clear()
  axios.post.mockReset()
  setOnAuthFailure(() => {})
})

describe('token storage helpers', () => {
  it('returns null when nothing is stored', () => {
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('setTokens stores both tokens', () => {
    setTokens({ access_token: 'access-1', refresh_token: 'refresh-1' })
    expect(getAccessToken()).toBe('access-1')
    expect(getRefreshToken()).toBe('refresh-1')
  })

  it('setTokens only writes the keys actually provided', () => {
    setTokens({ access_token: 'access-1', refresh_token: 'refresh-1' })
    setTokens({ access_token: 'access-2' })
    expect(getAccessToken()).toBe('access-2')
    expect(getRefreshToken()).toBe('refresh-1')
  })

  it('clearTokens removes both', () => {
    setTokens({ access_token: 'a', refresh_token: 'b' })
    clearTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })
})

describe('ApiError', () => {
  it('defaults status/code to null and details to an empty object', () => {
    const err = new ApiError('boom')
    expect(err.message).toBe('boom')
    expect(err.name).toBe('ApiError')
    expect(err.status).toBeNull()
    expect(err.code).toBeNull()
    expect(err.details).toEqual({})
  })

  it('carries the given status/code/details', () => {
    const err = new ApiError('bad', { status: 400, code: 'validation_error', details: { name: 'required' } })
    expect(err.status).toBe(400)
    expect(err.code).toBe('validation_error')
    expect(err.details).toEqual({ name: 'required' })
  })
})

describe('request interceptor', () => {
  it('leaves the config alone when there is no token', () => {
    const config = requestInterceptor({ headers: {} })
    expect(config.headers.Authorization).toBeUndefined()
  })

  it('attaches Authorization: Bearer <token> when a token is stored', () => {
    setTokens({ access_token: 'my-token' })
    const config = requestInterceptor({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer my-token')
  })

  it('also attaches the token as a query param in dev builds', () => {
    // bin/proxy-server.js strips the Authorization header locally, so
    // _shared/auth.py falls back to ?token=... when IS_LOCAL is true —
    // this only matters in dev builds (import.meta.env.DEV), which is the
    // mode Vitest itself runs under.
    setTokens({ access_token: 'my-token' })
    const config = requestInterceptor({ headers: {} })
    expect(config.params.token).toBe('my-token')
  })

  it('merges the token param with any params already on the request', () => {
    setTokens({ access_token: 'my-token' })
    const config = requestInterceptor({ headers: {}, params: { q: 'search' } })
    expect(config.params).toEqual({ q: 'search', token: 'my-token' })
  })
})

describe('response success interceptor', () => {
  it('unwraps the {data, meta} envelope onto response.data/.meta', () => {
    const response = { data: { data: [{ id: 1 }], meta: { total: 1 } } }
    const result = responseSuccess(response)
    expect(result.data).toEqual([{ id: 1 }])
    expect(result.meta).toEqual({ total: 1 })
  })

  it('unwraps even when there is no meta (single-record responses)', () => {
    const response = { data: { data: { id: 1 } } }
    const result = responseSuccess(response)
    expect(result.data).toEqual({ id: 1 })
    expect(result.meta).toBeUndefined()
  })

  it('leaves a response with no `data` envelope untouched', () => {
    const response = { data: 'not-an-envelope' }
    const result = responseSuccess(response)
    expect(result.data).toBe('not-an-envelope')
  })
})

describe('response error interceptor', () => {
  it('maps a network error (no response) to a status-0 ApiError', async () => {
    await expect(responseError({ message: 'Network Error' })).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining('Network error'),
    })
  })

  it('maps a backend error envelope to a matching ApiError', async () => {
    const error = {
      config: { url: '/teams-service', _retried: false },
      response: {
        status: 400,
        data: { error: { code: 'validation_error', message: 'One or more fields are invalid', details: { name: 'is required' } } },
      },
    }
    await expect(responseError(error)).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      message: 'One or more fields are invalid',
      details: { name: 'is required' },
    })
  })

  it('does not attempt a refresh for a 401 on the login route itself', async () => {
    const error = {
      config: { url: '/auth-service/login', _retried: false },
      response: { status: 401, data: { error: { code: 'invalid_credentials', message: 'Email or password is incorrect' } } },
    }
    await expect(responseError(error)).rejects.toMatchObject({ code: 'invalid_credentials' })
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('refreshes the token and retries the original request on a 401 elsewhere', async () => {
    setTokens({ access_token: 'expired', refresh_token: 'valid-refresh' })
    axios.post.mockResolvedValueOnce({
      data: { data: { access_token: 'fresh-token' } },
    })

    const config = { url: '/teams-service', headers: {}, _retried: false }
    const error = { config, response: { status: 401, data: {} } }

    const result = await responseError(error)

    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining('/auth-service/refresh'), {
      refresh_token: 'valid-refresh',
    })
    expect(getAccessToken()).toBe('fresh-token')
    expect(config.headers.Authorization).toBe('Bearer fresh-token')
    // api(config) resolves via the mocked axios instance, which for this
    // test doesn't stub a real response — the important assertions are the
    // refresh call and the retried config's own new Authorization header.
    expect(result).toBeDefined()
  })

  it('clears tokens and reports auth failure when the refresh itself fails', async () => {
    setTokens({ access_token: 'expired', refresh_token: 'stale-refresh' })
    axios.post.mockRejectedValueOnce({ response: { status: 401, data: {} } })
    const onAuthFailure = vi.fn()
    setOnAuthFailure(onAuthFailure)

    const config = { url: '/teams-service', headers: {}, _retried: false }
    const error = { config, response: { status: 401, data: {} } }

    await expect(responseError(error)).rejects.toBeInstanceOf(ApiError)
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(onAuthFailure).toHaveBeenCalledOnce()
  })

  it('does not attempt a second refresh once a request has already retried', async () => {
    const config = { url: '/teams-service', headers: {}, _retried: true }
    const error = { config, response: { status: 401, data: {} } }

    await expect(responseError(error)).rejects.toBeInstanceOf(ApiError)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('rejects immediately when there is no refresh token to use', async () => {
    setTokens({ access_token: 'expired' })
    const config = { url: '/teams-service', headers: {}, _retried: false }
    const error = { config, response: { status: 401, data: {} } }

    await expect(responseError(error)).rejects.toBeInstanceOf(ApiError)
    expect(axios.post).not.toHaveBeenCalled()
  })
})
