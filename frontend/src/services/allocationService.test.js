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

import {
  createAllocation,
  deleteAllocation,
  getAllocation,
  listAllocations,
  updateAllocation,
} from './allocationService'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('listAllocations', () => {
  it('GETs /allocations-service with params and shapes {allocations, meta}', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'a1' }], meta: { total: 1 } })
    const result = await listAllocations({ user_id: 'u1' })
    expect(mockGet).toHaveBeenCalledWith('/allocations-service', { params: { user_id: 'u1' } })
    expect(result).toEqual({ allocations: [{ id: 'a1' }], meta: { total: 1 } })
  })
})

describe('getAllocation', () => {
  it('GETs /allocations-service/{id} and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: { id: 'a1' } })
    const result = await getAllocation('a1')
    expect(mockGet).toHaveBeenCalledWith('/allocations-service/a1')
    expect(result).toEqual({ id: 'a1' })
  })
})

describe('createAllocation', () => {
  it('POSTs the payload to /allocations-service and returns res.data', async () => {
    const payload = { user_id: 'u1', project_id: 'p1', start_date: '2027-01-01', end_date: '2027-03-01' }
    mockPost.mockResolvedValue({ data: { id: 'a1', ...payload } })
    const result = await createAllocation(payload)
    expect(mockPost).toHaveBeenCalledWith('/allocations-service', payload)
    expect(result).toEqual({ id: 'a1', ...payload })
  })
})

describe('updateAllocation', () => {
  it('PUTs the payload to /allocations-service/{id} and returns res.data', async () => {
    const payload = { end_date: '2027-04-01' }
    mockPut.mockResolvedValue({ data: { id: 'a1', ...payload } })
    const result = await updateAllocation('a1', payload)
    expect(mockPut).toHaveBeenCalledWith('/allocations-service/a1', payload)
    expect(result).toEqual({ id: 'a1', end_date: '2027-04-01' })
  })
})

describe('deleteAllocation', () => {
  it('DELETEs /allocations-service/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteAllocation('a1')
    expect(mockDelete).toHaveBeenCalledWith('/allocations-service/a1')
  })
})
