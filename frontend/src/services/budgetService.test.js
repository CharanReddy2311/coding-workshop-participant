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
  createBudgetItem,
  createExpense,
  deleteBudgetItem,
  deleteExpense,
  getBudgetSummary,
  listBudgetItems,
  listExpenses,
  updateBudgetItem,
} from './budgetService'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('getBudgetSummary', () => {
  it('GETs /budget-service/summary and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: [{ project_code: 'PR01', consumed: 40, planned_budget: 100 }] })
    const result = await getBudgetSummary()
    expect(mockGet).toHaveBeenCalledWith('/budget-service/summary')
    expect(result).toEqual([{ project_code: 'PR01', consumed: 40, planned_budget: 100 }])
  })
})

describe('listBudgetItems', () => {
  it('GETs /budget-service/items with params and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'i1' }] })
    const result = await listBudgetItems({ project_id: 'p1' })
    expect(mockGet).toHaveBeenCalledWith('/budget-service/items', { params: { project_id: 'p1' } })
    expect(result).toEqual([{ id: 'i1' }])
  })

  it('defaults params to {} when omitted', async () => {
    mockGet.mockResolvedValue({ data: [] })
    await listBudgetItems()
    expect(mockGet).toHaveBeenCalledWith('/budget-service/items', { params: {} })
  })
})

describe('createBudgetItem', () => {
  it('POSTs the payload to /budget-service/items and returns res.data', async () => {
    const payload = { project_id: 'p1', category: 'Cloud', planned_amount: 3000 }
    mockPost.mockResolvedValue({ data: { id: 'i1', ...payload } })
    const result = await createBudgetItem(payload)
    expect(mockPost).toHaveBeenCalledWith('/budget-service/items', payload)
    expect(result).toEqual({ id: 'i1', ...payload })
  })
})

describe('updateBudgetItem', () => {
  it('PUTs the payload to /budget-service/items/{id} and returns res.data', async () => {
    mockPut.mockResolvedValue({ data: { id: 'i1', planned_amount: 5000 } })
    const result = await updateBudgetItem('i1', { planned_amount: 5000 })
    expect(mockPut).toHaveBeenCalledWith('/budget-service/items/i1', { planned_amount: 5000 })
    expect(result).toEqual({ id: 'i1', planned_amount: 5000 })
  })
})

describe('deleteBudgetItem', () => {
  it('DELETEs /budget-service/items/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteBudgetItem('i1')
    expect(mockDelete).toHaveBeenCalledWith('/budget-service/items/i1')
  })
})

describe('listExpenses', () => {
  it('GETs /budget-service/expenses with params and returns res.data', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'e1' }] })
    const result = await listExpenses({ project_id: 'p1' })
    expect(mockGet).toHaveBeenCalledWith('/budget-service/expenses', { params: { project_id: 'p1' } })
    expect(result).toEqual([{ id: 'e1' }])
  })

  it('defaults params to {} when omitted', async () => {
    mockGet.mockResolvedValue({ data: [] })
    await listExpenses()
    expect(mockGet).toHaveBeenCalledWith('/budget-service/expenses', { params: {} })
  })
})

describe('createExpense', () => {
  it('POSTs the payload to /budget-service/expenses and returns res.data', async () => {
    const payload = { budget_item_id: 'i1', amount: 500, incurred_on: '2027-02-01' }
    mockPost.mockResolvedValue({ data: { id: 'e1', ...payload } })
    const result = await createExpense(payload)
    expect(mockPost).toHaveBeenCalledWith('/budget-service/expenses', payload)
    expect(result).toEqual({ id: 'e1', ...payload })
  })
})

describe('deleteExpense', () => {
  it('DELETEs /budget-service/expenses/{id}', async () => {
    mockDelete.mockResolvedValue(undefined)
    await deleteExpense('e1')
    expect(mockDelete).toHaveBeenCalledWith('/budget-service/expenses/e1')
  })
})
