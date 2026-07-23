import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('./api', () => ({ default: { get: mockGet } }))

import { fetchDepartments, fetchUsers } from './directoryService'

beforeEach(() => {
  mockGet.mockReset()
})

describe('fetchDepartments', () => {
  it('GETs /directory-service/departments and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'dept-1', name: 'Engineering' }] })
    const result = await fetchDepartments()
    expect(mockGet).toHaveBeenCalledWith('/directory-service/departments')
    expect(result).toEqual([{ id: 'dept-1', name: 'Engineering' }])
  })
})

describe('fetchUsers', () => {
  it('GETs /directory-service/users and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'user-1', full_name: 'Ada Lovelace' }] })
    const result = await fetchUsers()
    expect(mockGet).toHaveBeenCalledWith('/directory-service/users')
    expect(result).toEqual([{ id: 'user-1', full_name: 'Ada Lovelace' }])
  })
})
