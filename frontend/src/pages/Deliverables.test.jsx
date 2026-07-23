import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Deliverables from './Deliverables'

// Deliverables.jsx unconditionally renders <DeliverableFormDialog> (its own
// effects fire fetchUsers/listProjects even closed) and <AppLayout> — every
// service either page touches needs mocking here too.
const {
  mockUseAuth,
  mockListDeliverables,
  mockDeleteDeliverable,
  mockCreateDeliverable,
  mockUpdateDeliverable,
  mockListDependencies,
  mockAddDependency,
  mockRemoveDependency,
  mockFetchUsers,
  mockListProjects,
} = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockListDeliverables: vi.fn(),
  mockDeleteDeliverable: vi.fn(),
  mockCreateDeliverable: vi.fn(),
  mockUpdateDeliverable: vi.fn(),
  mockListDependencies: vi.fn(),
  mockAddDependency: vi.fn(),
  mockRemoveDependency: vi.fn(),
  mockFetchUsers: vi.fn(),
  mockListProjects: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../services/deliverableService', () => ({
  listDeliverables: (...args) => mockListDeliverables(...args),
  deleteDeliverable: (...args) => mockDeleteDeliverable(...args),
  createDeliverable: (...args) => mockCreateDeliverable(...args),
  updateDeliverable: (...args) => mockUpdateDeliverable(...args),
  listDependencies: (...args) => mockListDependencies(...args),
  addDependency: (...args) => mockAddDependency(...args),
  removeDependency: (...args) => mockRemoveDependency(...args),
}))
vi.mock('../services/directoryService', () => ({
  fetchUsers: (...args) => mockFetchUsers(...args),
}))
vi.mock('../services/projectService', () => ({
  listProjects: (...args) => mockListProjects(...args),
}))

const today = new Date().toISOString().slice(0, 10)

// Stub the form dialog so the page's own open/save/close handlers run without
// mounting the real dialog (covered by its own test file).
vi.mock('../components/DeliverableFormDialog', () => ({
  default: ({ open, deliverable, onClose, onSaved }) =>
    open ? (
      <div>
        <p>{`stub-dialog:${deliverable ? 'edit' : 'create'}`}</p>
        <button onClick={() => onSaved({ id: 'd9', name: 'Saved Deliverable' })}>stub-save</button>
        <button onClick={onClose}>stub-close</button>
      </div>
    ) : null,
}))

const SAMPLE_DELIVERABLES = [
  {
    id: 'd1',
    name: 'Design Doc',
    description: 'Initial draft',
    project_code: 'PR01',
    project_name: 'Expense Tracker',
    owner_name: 'Ada Lovelace',
    status: 'IN_PROGRESS',
    percent_complete: 40,
    due_date: '2000-01-01',
  },
  {
    id: 'd2',
    name: 'Rollout',
    description: null,
    project_code: 'PR02',
    project_name: 'Payroll',
    owner_name: null,
    status: 'COMPLETED',
    percent_complete: 100,
    due_date: today,
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

function renderDeliverables() {
  return render(
    <MemoryRouter>
      <Deliverables />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockListDeliverables.mockReset()
  mockDeleteDeliverable.mockReset()
  mockCreateDeliverable.mockReset()
  mockUpdateDeliverable.mockReset()
  mockListDependencies.mockReset().mockResolvedValue({ predecessors: [], successors: [] })
  mockAddDependency.mockReset()
  mockRemoveDependency.mockReset()
  mockFetchUsers.mockReset().mockResolvedValue([])
  mockListProjects.mockReset().mockResolvedValue({ projects: [], meta: { total: 0 } })
  mockListDeliverables.mockResolvedValue({
    deliverables: SAMPLE_DELIVERABLES,
    meta: { total: 2, limit: 10, offset: 0 },
  })
  authAs('ADMIN')
})

describe('list rendering', () => {
  it('renders every deliverable with project, owner, status, progress, and due date', async () => {
    renderDeliverables()

    expect(await screen.findByText('Design Doc')).toBeInTheDocument()
    expect(screen.getByText('Initial draft')).toBeInTheDocument()
    expect(screen.getByText('PR01 — Expense Tracker')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('IN PROGRESS')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()

    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('flags a past-due open deliverable as overdue', async () => {
    renderDeliverables()
    expect(await screen.findByText('2000-01-01 (overdue)')).toBeInTheDocument()
  })

  it('shows an empty state when there are no deliverables', async () => {
    mockListDeliverables.mockResolvedValue({ deliverables: [], meta: { total: 0, limit: 10, offset: 0 } })
    renderDeliverables()
    expect(await screen.findByText('No deliverables found.')).toBeInTheDocument()
  })

  it('shows an error alert when the list request fails', async () => {
    mockListDeliverables.mockRejectedValue(new Error('Failed to load deliverables'))
    renderDeliverables()
    expect(await screen.findByText('Failed to load deliverables')).toBeInTheDocument()
  })

  it('debounces search input into a q parameter', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    mockListDeliverables.mockClear()

    await userEvent.type(screen.getByLabelText(/search by name/i), 'design')

    await waitFor(
      () => expect(mockListDeliverables).toHaveBeenCalledWith(expect.objectContaining({ q: 'design' })),
      { timeout: 2000 },
    )
  })
})

describe('RBAC-gated actions', () => {
  it('disables Create, Edit, and Delete for a Viewer', async () => {
    authAs('VIEWER')
    renderDeliverables()
    await screen.findByText('Design Doc')

    expect(screen.getByRole('button', { name: /create deliverable/i })).toBeDisabled()
    const rows = screen.getAllByRole('row').slice(1)
    within(rows[0])
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeDisabled())
  })

  it('allows creating and editing but not deleting for a Contributor', async () => {
    authAs('CONTRIBUTOR')
    renderDeliverables()
    await screen.findByText('Design Doc')

    expect(screen.getByRole('button', { name: /create deliverable/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [editButton, deleteButton] = within(firstRow).getAllByRole('button')
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeDisabled()
  })

  it('enables every action for an Admin', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')

    const firstRow = screen.getAllByRole('row')[1]
    within(firstRow)
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeEnabled())
  })
})

describe('delete flow', () => {
  it('confirms before deleting, then removes the deliverable and shows a snackbar', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    expect(await screen.findByText('Delete deliverable?')).toBeInTheDocument()

    mockDeleteDeliverable.mockResolvedValue(undefined)
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mockDeleteDeliverable).toHaveBeenCalledWith('d1'))
    expect(await screen.findByText('Deliverable "Design Doc" deleted')).toBeInTheDocument()
  })

  it('shows the backend error inside the confirm dialog when delete fails', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    mockDeleteDeliverable.mockRejectedValue(new Error('Failed to delete deliverable'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Failed to delete deliverable')).toBeInTheDocument()
  })
})

describe('dialog interactions', () => {
  it('opens the create dialog', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    await userEvent.click(screen.getByRole('button', { name: /create deliverable/i }))
    expect(screen.getByText('stub-dialog:create')).toBeInTheDocument()
  })

  it('opens the edit dialog for a row', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    const [editButton] = within(screen.getAllByRole('row')[1]).getAllByRole('button')
    await userEvent.click(editButton)
    expect(screen.getByText('stub-dialog:edit')).toBeInTheDocument()
  })

  it('shows a snackbar after saving from the dialog', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    await userEvent.click(screen.getByRole('button', { name: /create deliverable/i }))
    await userEvent.click(screen.getByRole('button', { name: 'stub-save' }))
    expect(await screen.findByText('Deliverable "Saved Deliverable" created')).toBeInTheDocument()
  })

  it('closes the dialog without saving', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    await userEvent.click(screen.getByRole('button', { name: /create deliverable/i }))
    await userEvent.click(screen.getByRole('button', { name: 'stub-close' }))
    expect(screen.queryByText('stub-dialog:create')).not.toBeInTheDocument()
  })
})

describe('pagination and delete-cancel', () => {
  it('requests the next page of results', async () => {
    mockListDeliverables.mockResolvedValue({ deliverables: SAMPLE_DELIVERABLES, meta: { total: 100, limit: 10, offset: 0 } })
    renderDeliverables()
    await screen.findByText('Design Doc')
    await userEvent.click(screen.getByRole('button', { name: /go to next page/i }))
    await waitFor(() => expect(mockListDeliverables).toHaveBeenCalledWith(expect.objectContaining({ offset: 10 })))
  })

  it('cancels the delete confirmation', async () => {
    renderDeliverables()
    await screen.findByText('Design Doc')
    const [, deleteButton] = within(screen.getAllByRole('row')[1]).getAllByRole('button')
    await userEvent.click(deleteButton)
    expect(await screen.findByText('Delete deliverable?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByText('Delete deliverable?')).not.toBeInTheDocument())
  })
})
