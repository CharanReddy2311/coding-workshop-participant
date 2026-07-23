import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Allocations from './Allocations'

const {
  mockUseAuth,
  mockListAllocations,
  mockDeleteAllocation,
  mockCreateAllocation,
  mockUpdateAllocation,
  mockFetchUsers,
  mockListProjects,
} = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockListAllocations: vi.fn(),
  mockDeleteAllocation: vi.fn(),
  mockCreateAllocation: vi.fn(),
  mockUpdateAllocation: vi.fn(),
  mockFetchUsers: vi.fn(),
  mockListProjects: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../services/allocationService', () => ({
  listAllocations: (...args) => mockListAllocations(...args),
  deleteAllocation: (...args) => mockDeleteAllocation(...args),
  createAllocation: (...args) => mockCreateAllocation(...args),
  updateAllocation: (...args) => mockUpdateAllocation(...args),
}))
vi.mock('../services/directoryService', () => ({
  fetchUsers: (...args) => mockFetchUsers(...args),
}))
vi.mock('../services/projectService', () => ({
  listProjects: (...args) => mockListProjects(...args),
}))

const today = new Date().toISOString().slice(0, 10)

const SAMPLE_ALLOCATIONS = [
  {
    id: 'a1',
    user_name: 'Ada Lovelace',
    user_email: 'ada@example.com',
    project_code: 'PR01',
    project_name: 'Expense Tracker',
    role_on_project: 'Tech Lead',
    allocation_pct: 50,
    start_date: '2000-01-01',
    end_date: today,
  },
  {
    id: 'a2',
    user_name: 'Grace Hopper',
    user_email: 'grace@example.com',
    project_code: 'PR02',
    project_name: 'Payroll',
    role_on_project: null,
    allocation_pct: 25,
    start_date: '1999-01-01',
    end_date: '1999-06-01',
  },
]

function authAs(role) {
  const RANK = { VIEWER: 0, CONTRIBUTOR: 1, MANAGER: 2, ADMIN: 3 }
  mockUseAuth.mockReturnValue({
    user: { id: 'u1', full_name: 'Test User', email: 'test@example.com', role },
    logout: vi.fn(),
    hasRole: (min) => RANK[role] >= RANK[min],
  })
}

function renderAllocations() {
  return render(
    <MemoryRouter>
      <Allocations />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockListAllocations.mockReset()
  mockDeleteAllocation.mockReset()
  mockCreateAllocation.mockReset()
  mockUpdateAllocation.mockReset()
  mockFetchUsers.mockReset().mockResolvedValue([])
  mockListProjects.mockReset().mockResolvedValue({ projects: [], meta: { total: 0 } })
  mockListAllocations.mockResolvedValue({
    allocations: SAMPLE_ALLOCATIONS,
    meta: { total: 2, limit: 10, offset: 0 },
  })
  authAs('ADMIN')
})

describe('list rendering', () => {
  it('renders every allocation with user, project, role, percentage, and period', async () => {
    renderAllocations()

    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('ada@example.com')).toBeInTheDocument()
    expect(screen.getByText('PR01 — Expense Tracker')).toBeInTheDocument()
    expect(screen.getByText('Tech Lead')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText(`2000-01-01 → ${today}`)).toBeInTheDocument()

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('shows an empty state when there are no allocations', async () => {
    mockListAllocations.mockResolvedValue({ allocations: [], meta: { total: 0, limit: 10, offset: 0 } })
    renderAllocations()
    expect(await screen.findByText('No allocations found.')).toBeInTheDocument()
  })

  it('shows an error alert when the list request fails', async () => {
    mockListAllocations.mockRejectedValue(new Error('Failed to load allocations'))
    renderAllocations()
    expect(await screen.findByText('Failed to load allocations')).toBeInTheDocument()
  })

  it('filters by user', async () => {
    mockFetchUsers.mockResolvedValue([{ id: 'user-1', full_name: 'Ada Lovelace' }])
    renderAllocations()
    await screen.findByText('Ada Lovelace')
    mockListAllocations.mockClear()

    await userEvent.click(screen.getByRole('combobox', { name: /^user/i }))
    await userEvent.click(within(await screen.findByRole('listbox')).getByText('Ada Lovelace'))

    await waitFor(() =>
      expect(mockListAllocations).toHaveBeenCalledWith(expect.objectContaining({ user_id: 'user-1' })),
    )
  })
})

describe('RBAC-gated actions', () => {
  it('disables Create, Edit, and Delete for a Viewer', async () => {
    authAs('VIEWER')
    renderAllocations()
    await screen.findByText('Ada Lovelace')

    expect(screen.getByRole('button', { name: /create allocation/i })).toBeDisabled()
    const rows = screen.getAllByRole('row').slice(1)
    within(rows[0])
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeDisabled())
  })

  it('allows creating and editing but not deleting for a Contributor', async () => {
    authAs('CONTRIBUTOR')
    renderAllocations()
    await screen.findByText('Ada Lovelace')

    expect(screen.getByRole('button', { name: /create allocation/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [editButton, deleteButton] = within(firstRow).getAllByRole('button')
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeDisabled()
  })

  it('enables every action for an Admin', async () => {
    renderAllocations()
    await screen.findByText('Ada Lovelace')

    const firstRow = screen.getAllByRole('row')[1]
    within(firstRow)
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeEnabled())
  })
})

describe('delete flow', () => {
  it('confirms before deleting, then removes the allocation and shows a snackbar', async () => {
    renderAllocations()
    await screen.findByText('Ada Lovelace')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    expect(await screen.findByText('Delete allocation?')).toBeInTheDocument()

    mockDeleteAllocation.mockResolvedValue(undefined)
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mockDeleteAllocation).toHaveBeenCalledWith('a1'))
    expect(await screen.findByText('Allocation deleted')).toBeInTheDocument()
  })

  it('shows the backend error inside the confirm dialog when delete fails', async () => {
    renderAllocations()
    await screen.findByText('Ada Lovelace')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    mockDeleteAllocation.mockRejectedValue(new Error('Failed to delete allocation'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Failed to delete allocation')).toBeInTheDocument()
  })
})
