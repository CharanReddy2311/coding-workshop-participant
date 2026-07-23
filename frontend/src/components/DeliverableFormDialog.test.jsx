import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DeliverableFormDialog from './DeliverableFormDialog'

const {
  MockApiError,
  mockCreateDeliverable,
  mockUpdateDeliverable,
  mockListDeliverables,
  mockListDependencies,
  mockAddDependency,
  mockRemoveDependency,
  mockFetchUsers,
  mockListProjects,
} = vi.hoisted(() => {
  class MockApiError extends Error {
    constructor(message, { status, code, details } = {}) {
      super(message)
      this.name = 'ApiError'
      this.status = status ?? null
      this.code = code ?? null
      this.details = details || {}
    }
  }
  return {
    MockApiError,
    mockCreateDeliverable: vi.fn(),
    mockUpdateDeliverable: vi.fn(),
    mockListDeliverables: vi.fn(),
    mockListDependencies: vi.fn(),
    mockAddDependency: vi.fn(),
    mockRemoveDependency: vi.fn(),
    mockFetchUsers: vi.fn(),
    mockListProjects: vi.fn(),
  }
})

vi.mock('../services/api', () => ({ ApiError: MockApiError }))
vi.mock('../services/deliverableService', () => ({
  createDeliverable: (...args) => mockCreateDeliverable(...args),
  updateDeliverable: (...args) => mockUpdateDeliverable(...args),
  listDeliverables: (...args) => mockListDeliverables(...args),
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

const PROJECTS = [{ id: 'proj-1', code: 'PR01', name: 'Expense Tracker' }]
const USERS = [{ id: 'user-1', full_name: 'Ada Lovelace', email: 'ada@example.com' }]

async function selectOption(labelPattern, optionText) {
  const combobox = screen.getByRole('combobox', { name: labelPattern })
  await userEvent.click(combobox)
  const listbox = await screen.findByRole('listbox')
  await userEvent.click(within(listbox).getByText(optionText))
}

async function fillRequiredFieldsForCreate() {
  await waitFor(() => expect(mockListProjects).toHaveBeenCalled())
  await selectOption(/^project/i, 'PR01 — Expense Tracker')
  await userEvent.type(screen.getByLabelText(/^name/i), 'Design Doc')
  fireEvent.change(screen.getByLabelText(/due date/i), { target: { value: '2027-06-01' } })
}

beforeEach(() => {
  mockCreateDeliverable.mockReset()
  mockUpdateDeliverable.mockReset()
  mockListDeliverables.mockReset().mockResolvedValue({ deliverables: [], meta: { total: 0 } })
  mockListDependencies.mockReset().mockResolvedValue({ predecessors: [], successors: [] })
  mockAddDependency.mockReset()
  mockRemoveDependency.mockReset()
  mockFetchUsers.mockReset().mockResolvedValue(USERS)
  mockListProjects.mockReset().mockResolvedValue({ projects: PROJECTS, meta: { total: 1 } })
})

describe('create mode', () => {
  it('renders the create title, NOT_STARTED default, and disabled submit', async () => {
    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Create Deliverable' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /^status/i })).toHaveTextContent('NOT STARTED')
    await waitFor(() => expect(mockListProjects).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Create Deliverable' })).toBeDisabled()
  })

  it('does not render the Dependencies section when creating', async () => {
    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(mockListProjects).toHaveBeenCalled())
    expect(screen.queryByText('Dependencies')).not.toBeInTheDocument()
  })

  it('enables submit once project, name (2+ chars), and due date are set', async () => {
    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await fillRequiredFieldsForCreate()
    expect(screen.getByRole('button', { name: 'Create Deliverable' })).toBeEnabled()
  })

  it('submits the expected payload with owner_id/completed_at defaulted to null', async () => {
    const onSaved = vi.fn()
    const created = { id: 'd1' }
    mockCreateDeliverable.mockResolvedValue(created)

    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={onSaved} />)
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Deliverable' }))

    await waitFor(() =>
      expect(mockCreateDeliverable).toHaveBeenCalledWith({
        project_id: 'proj-1',
        owner_id: null,
        name: 'Design Doc',
        description: null,
        status: 'NOT_STARTED',
        percent_complete: 0,
        weight: 1,
        due_date: '2027-06-01',
        completed_at: null,
      }),
    )
    expect(onSaved).toHaveBeenCalledWith(created)
  })

  it('surfaces field-level errors from a validation failure', async () => {
    mockCreateDeliverable.mockRejectedValue(
      new MockApiError('One or more fields are invalid', {
        status: 400,
        details: { completed_at: 'is required when marked completed' },
      }),
    )

    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Deliverable' }))

    expect(await screen.findByText('One or more fields are invalid')).toBeInTheDocument()
    expect(screen.getByText('is required when marked completed')).toBeInTheDocument()
  })

  it('shows a generic message for a non-ApiError failure', async () => {
    mockCreateDeliverable.mockRejectedValue(new Error('kaboom'))
    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Deliverable' }))
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
  })

  it('shows a warning when the dropdown options fail to load', async () => {
    mockListProjects.mockRejectedValue(new MockApiError('Network error', { status: 0 }))
    render(<DeliverableFormDialog open deliverable={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(await screen.findByText('Network error')).toBeInTheDocument()
  })
})

describe('edit mode', () => {
  const existingDeliverable = {
    id: 'd1',
    project_id: 'proj-1',
    project_code: 'PR01',
    project_name: 'Expense Tracker',
    owner_id: 'user-1',
    owner_name: 'Ada Lovelace',
    name: 'Design Doc',
    description: 'Initial draft',
    status: 'IN_PROGRESS',
    percent_complete: 40,
    weight: 2,
    due_date: '2027-06-01',
    completed_at: '',
  }

  it('renders the edit title with the deliverable name and pre-fills fields', async () => {
    render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Edit Design Doc' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^name/i)).toHaveValue('Design Doc')
    expect(screen.getByLabelText(/% complete/i)).toHaveValue(40)
    expect(screen.getByLabelText(/weight/i)).toHaveValue(2)
    await waitFor(() => expect(mockListProjects).toHaveBeenCalled())
    expect(screen.getByRole('combobox', { name: /^status/i })).toHaveTextContent('IN PROGRESS')
  })

  it('submits an update via updateDeliverable', async () => {
    mockUpdateDeliverable.mockResolvedValue({ ...existingDeliverable, status: 'COMPLETED' })
    const onSaved = vi.fn()

    render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(mockListProjects).toHaveBeenCalled())
    await selectOption(/^status/i, 'COMPLETED')
    await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() =>
      expect(mockUpdateDeliverable).toHaveBeenCalledWith(
        'd1',
        expect.objectContaining({ name: 'Design Doc', status: 'COMPLETED' }),
      ),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  describe('dependencies section', () => {
    it('loads and renders predecessors and successors', async () => {
      mockListDependencies.mockResolvedValue({
        predecessors: [{ id: 'd2', name: 'Kickoff', status: 'COMPLETED', due_date: '2027-01-01', dep_type: 'FINISH_TO_START' }],
        successors: [{ id: 'd3', name: 'Rollout', status: 'NOT_STARTED', due_date: '2027-07-01', dep_type: 'FINISH_TO_START' }],
      })

      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)

      expect(await screen.findByText('Kickoff')).toBeInTheDocument()
      expect(screen.getByText('Rollout')).toBeInTheDocument()
      expect(screen.getByText(/COMPLETED · due 2027-01-01 · FINISH TO START/)).toBeInTheDocument()
    })

    it('shows empty-state copy when there are no predecessors or successors', async () => {
      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      expect(await screen.findByText('Nothing blocking this deliverable.')).toBeInTheDocument()
      expect(screen.getByText('Nothing depends on this deliverable.')).toBeInTheDocument()
    })

    it('adds a predecessor dependency and refreshes the list', async () => {
      mockListDeliverables.mockResolvedValue({
        deliverables: [{ id: 'd2', name: 'Kickoff' }, { id: 'd1', name: 'Design Doc' }],
        meta: { total: 2 },
      })
      mockAddDependency.mockResolvedValue({ id: 'edge1' })

      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      await screen.findByText('Nothing blocking this deliverable.')

      await selectOption(/add predecessor/i, 'Kickoff')
      await userEvent.click(screen.getByRole('button', { name: 'Add' }))

      await waitFor(() =>
        expect(mockAddDependency).toHaveBeenCalledWith('d1', {
          predecessor_id: 'd2',
          dep_type: 'FINISH_TO_START',
        }),
      )
    })

    it('removes a predecessor edge', async () => {
      mockListDependencies.mockResolvedValue({
        predecessors: [{ id: 'd2', name: 'Kickoff', status: 'COMPLETED', due_date: '2027-01-01', dep_type: 'FINISH_TO_START' }],
        successors: [],
      })
      mockRemoveDependency.mockResolvedValue(undefined)

      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      const item = (await screen.findByText('Kickoff')).closest('li')

      await userEvent.click(within(item).getByRole('button'))

      await waitFor(() => expect(mockRemoveDependency).toHaveBeenCalledWith('d1', 'd2'))
    })

    it('removes a successor edge by deleting on the successor itself', async () => {
      mockListDependencies.mockResolvedValue({
        predecessors: [],
        successors: [{ id: 'd3', name: 'Rollout', status: 'NOT_STARTED', due_date: '2027-07-01', dep_type: 'FINISH_TO_START' }],
      })
      mockRemoveDependency.mockResolvedValue(undefined)

      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      const item = (await screen.findByText('Rollout')).closest('li')

      await userEvent.click(within(item).getByRole('button'))

      await waitFor(() => expect(mockRemoveDependency).toHaveBeenCalledWith('d3', 'd1'))
    })

    it('shows an error when the dependency list fails to load', async () => {
      mockListDependencies.mockRejectedValue(new Error('Could not load dependencies'))
      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      expect(await screen.findByText('Could not load dependencies')).toBeInTheDocument()
    })

    it('disables Add while no candidate is selected', async () => {
      render(<DeliverableFormDialog open deliverable={existingDeliverable} onClose={vi.fn()} onSaved={vi.fn()} />)
      await screen.findByText('Nothing blocking this deliverable.')
      expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    })
  })
})
