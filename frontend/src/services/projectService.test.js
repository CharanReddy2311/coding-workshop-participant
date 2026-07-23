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

import { createProject, deleteProject, getProject, listProjects, updateProject } from './projectService'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('listProjects', () => {
  it('GETs /projects-service with params and shapes {projects, meta}', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'p1' }], meta: { total: 1 } })
    const result = await listProjects({ status: 'ACTIVE' })
    expect(mockGet).toHaveBeenCalledWith('/projects-service', { params: { status: 'ACTIVE' } })
    expect(result).toEqual({ projects: [{ id: 'p1' }], meta: { total: 1 } })
  })

  it('defaults params to {} when omitted', async () => {
    mockGet.mockResolvedValue({ data: [], meta: { total: 0 } })
    await listProjects()
    expect(mockGet).toHaveBeenCalledWith('/projects-service', { params: {} })
  })
})

describe('getProject', () => {
  it('GETs /projects-service/{id} and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: { id: 'p1', code: 'PR01' } })
    const result = await getProject('p1')
    expect(mockGet).toHaveBeenCalledWith('/projects-service/p1')
    expect(result).toEqual({ id: 'p1', code: 'PR01' })
  })
})

describe('createProject', () => {
  it('POSTs the payload to /projects-service and returns res.data', async () => {
    const payload = { code: 'PR05', name: 'New Project' }
    mockPost.mockResolvedValue({ data: { id: 'p1', ...payload } })
    const result = await createProject(payload)
    expect(mockPost).toHaveBeenCalledWith('/projects-service', payload)
    expect(result).toEqual({ id: 'p1', code: 'PR05', name: 'New Project' })
  })
})

describe('updateProject', () => {
  it('PUTs the payload to /projects-service/{id} and returns res.data', async () => {
    const payload = { priority: 'CRITICAL' }
    mockPut.mockResolvedValue({ data: { id: 'p1', ...payload } })
    const result = await updateProject('p1', payload)
    expect(mockPut).toHaveBeenCalledWith('/projects-service/p1', payload)
    expect(result).toEqual({ id: 'p1', priority: 'CRITICAL' })
  })
})

describe('deleteProject', () => {
  it('DELETEs /projects-service/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteProject('p1')
    expect(mockDelete).toHaveBeenCalledWith('/projects-service/p1')
  })
})
