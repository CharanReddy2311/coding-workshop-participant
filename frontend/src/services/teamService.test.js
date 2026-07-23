import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockGet, mockPost, mockPut, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockDelete: vi.fn(),
}))

vi.mock('./api', () => ({
  default: { get: mockGet, post: mockPost, put: mockPut, delete: mockDelete },
}))

import { createTeam, deleteTeam, getTeam, listTeams, updateTeam } from './teamService'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('listTeams', () => {
  it('GETs /teams-service with params and shapes {teams, meta}', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 't1' }], meta: { total: 1 } })
    const result = await listTeams({ q: 'platform' })
    expect(mockGet).toHaveBeenCalledWith('/teams-service', { params: { q: 'platform' } })
    expect(result).toEqual({ teams: [{ id: 't1' }], meta: { total: 1 } })
  })
})

describe('getTeam', () => {
  it('GETs /teams-service/{id} and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: { id: 't1', name: 'Platform' } })
    const result = await getTeam('t1')
    expect(mockGet).toHaveBeenCalledWith('/teams-service/t1')
    expect(result).toEqual({ id: 't1', name: 'Platform' })
  })
})

describe('createTeam', () => {
  it('POSTs the payload to /teams-service and returns res.data', async () => {
    const payload = { name: 'Platform Engineering' }
    mockPost.mockResolvedValue({ data: { id: 't1', ...payload } })
    const result = await createTeam(payload)
    expect(mockPost).toHaveBeenCalledWith('/teams-service', payload)
    expect(result).toEqual({ id: 't1', name: 'Platform Engineering' })
  })
})

describe('updateTeam', () => {
  it('PUTs the payload to /teams-service/{id} and returns res.data', async () => {
    const payload = { name: 'Renamed' }
    mockPut.mockResolvedValue({ data: { id: 't1', ...payload } })
    const result = await updateTeam('t1', payload)
    expect(mockPut).toHaveBeenCalledWith('/teams-service/t1', payload)
    expect(result).toEqual({ id: 't1', name: 'Renamed' })
  })
})

describe('deleteTeam', () => {
  it('DELETEs /teams-service/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteTeam('t1')
    expect(mockDelete).toHaveBeenCalledWith('/teams-service/t1')
  })
})
