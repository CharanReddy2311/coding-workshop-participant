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
  addDependency,
  createDeliverable,
  deleteDeliverable,
  getDeliverable,
  listDeliverables,
  listDependencies,
  removeDependency,
  updateDeliverable,
} from './deliverableService'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('listDeliverables', () => {
  it('GETs /deliverables-service with params and shapes {deliverables, meta}', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'd1' }], meta: { total: 1 } })
    const result = await listDeliverables({ project_id: 'p1' })
    expect(mockGet).toHaveBeenCalledWith('/deliverables-service', { params: { project_id: 'p1' } })
    expect(result).toEqual({ deliverables: [{ id: 'd1' }], meta: { total: 1 } })
  })
})

describe('getDeliverable', () => {
  it('GETs /deliverables-service/{id} and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: { id: 'd1' } })
    const result = await getDeliverable('d1')
    expect(mockGet).toHaveBeenCalledWith('/deliverables-service/d1')
    expect(result).toEqual({ id: 'd1' })
  })
})

describe('createDeliverable', () => {
  it('POSTs the payload to /deliverables-service and returns res.data', async () => {
    const payload = { name: 'Design Doc' }
    mockPost.mockResolvedValue({ data: { id: 'd1', ...payload } })
    const result = await createDeliverable(payload)
    expect(mockPost).toHaveBeenCalledWith('/deliverables-service', payload)
    expect(result).toEqual({ id: 'd1', name: 'Design Doc' })
  })
})

describe('updateDeliverable', () => {
  it('PUTs the payload to /deliverables-service/{id} and returns res.data', async () => {
    const payload = { status: 'DONE' }
    mockPut.mockResolvedValue({ data: { id: 'd1', ...payload } })
    const result = await updateDeliverable('d1', payload)
    expect(mockPut).toHaveBeenCalledWith('/deliverables-service/d1', payload)
    expect(result).toEqual({ id: 'd1', status: 'DONE' })
  })
})

describe('deleteDeliverable', () => {
  it('DELETEs /deliverables-service/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteDeliverable('d1')
    expect(mockDelete).toHaveBeenCalledWith('/deliverables-service/d1')
  })
})

describe('listDependencies', () => {
  it('GETs /deliverables-service/{id}/dependencies and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: { predecessors: [], successors: [] } })
    const result = await listDependencies('d1')
    expect(mockGet).toHaveBeenCalledWith('/deliverables-service/d1/dependencies')
    expect(result).toEqual({ predecessors: [], successors: [] })
  })
})

describe('addDependency', () => {
  it('POSTs the payload to /deliverables-service/{id}/dependencies and returns res.data', async () => {
    const payload = { predecessor_id: 'd2' }
    mockPost.mockResolvedValue({ data: { id: 'edge1' } })
    const result = await addDependency('d1', payload)
    expect(mockPost).toHaveBeenCalledWith('/deliverables-service/d1/dependencies', payload)
    expect(result).toEqual({ id: 'edge1' })
  })
})

describe('removeDependency', () => {
  it('DELETEs /deliverables-service/{id}/dependencies/{predecessorId}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await removeDependency('d1', 'd2')
    expect(mockDelete).toHaveBeenCalledWith('/deliverables-service/d1/dependencies/d2')
  })
})
