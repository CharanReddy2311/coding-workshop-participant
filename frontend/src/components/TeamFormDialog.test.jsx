import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TeamFormDialog from './TeamFormDialog'

const { MockApiError, mockCreateTeam, mockUpdateTeam, mockFetchDepartments, mockFetchUsers } = vi.hoisted(() => {
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
    mockCreateTeam: vi.fn(),
    mockUpdateTeam: vi.fn(),
    mockFetchDepartments: vi.fn(),
    mockFetchUsers: vi.fn(),
  }
})

vi.mock('../services/api', () => ({ ApiError: MockApiError }))
vi.mock('../services/teamService', () => ({
  createTeam: (...args) => mockCreateTeam(...args),
  updateTeam: (...args) => mockUpdateTeam(...args),
  fetchDepartments: (...args) => mockFetchDepartments(...args),
  fetchUsers: (...args) => mockFetchUsers(...args),
}))

const DEPARTMENTS = [
  { id: 'dept-1', name: 'Engineering' },
  { id: 'dept-2', name: 'Finance' },
]
const USERS = [{ id: 'user-1', full_name: 'Ada Lovelace', email: 'ada@example.com' }]

async function selectOption(labelPattern, optionText) {
  const combobox = screen.getByRole('combobox', { name: labelPattern })
  await userEvent.click(combobox)
  const listbox = await screen.findByRole('listbox')
  await userEvent.click(within(listbox).getByText(optionText))
}

beforeEach(() => {
  mockCreateTeam.mockReset()
  mockUpdateTeam.mockReset()
  mockFetchDepartments.mockReset().mockResolvedValue(DEPARTMENTS)
  mockFetchUsers.mockReset().mockResolvedValue(USERS)
})

describe('create mode', () => {
  it('renders the create title and an initially-disabled submit button', async () => {
    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Create Team' })).toBeInTheDocument()
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Create Team' })).toBeDisabled()
  })

  it('populates the department and manager dropdowns from directory-service', async () => {
    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    await selectOption(/department/i, 'Finance')
    await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')

    expect(screen.getByRole('combobox', { name: /department/i })).toHaveTextContent('Finance')
    expect(screen.getByRole('combobox', { name: /manager/i })).toHaveTextContent('Ada Lovelace')
  })

  it('shows a warning when the dropdown options fail to load', async () => {
    mockFetchDepartments.mockRejectedValue(new MockApiError('Network error', { status: 0 }))
    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(await screen.findByText('Network error')).toBeInTheDocument()
  })

  it('enables submit once name, department, and manager are all filled in', async () => {
    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())

    await userEvent.type(screen.getByLabelText(/^name/i), 'Platform Engineering')
    await selectOption(/department/i, 'Engineering')
    await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')

    expect(screen.getByRole('button', { name: 'Create Team' })).toBeEnabled()
  })

  it('submits the expected payload and calls onSaved with the created team', async () => {
    const onSaved = vi.fn()
    const createdTeam = { id: 't1', name: 'Platform Engineering' }
    mockCreateTeam.mockResolvedValue(createdTeam)

    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())

    await userEvent.type(screen.getByLabelText(/^name/i), 'Platform Engineering')
    await selectOption(/department/i, 'Engineering')
    await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Create Team' }))

    await waitFor(() => expect(mockCreateTeam).toHaveBeenCalledWith({
      name: 'Platform Engineering',
      description: null,
      department_id: 'dept-1',
      manager_id: 'user-1',
      is_active: true,
    }))
    expect(onSaved).toHaveBeenCalledWith(createdTeam)
  })

  it('surfaces field-level errors from a validation failure without calling onSaved', async () => {
    const onSaved = vi.fn()
    mockCreateTeam.mockRejectedValue(
      new MockApiError('One or more fields are invalid', {
        status: 400,
        details: { name: 'is already used by another team' },
      }),
    )

    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())

    await userEvent.type(screen.getByLabelText(/^name/i), 'Duplicate Team')
    await selectOption(/department/i, 'Engineering')
    await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Create Team' }))

    expect(await screen.findByText('One or more fields are invalid')).toBeInTheDocument()
    expect(screen.getByText('is already used by another team')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('shows a generic message for a non-ApiError failure', async () => {
    mockCreateTeam.mockRejectedValue(new Error('kaboom'))

    render(<TeamFormDialog open team={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())

    await userEvent.type(screen.getByLabelText(/^name/i), 'Whatever Team')
    await selectOption(/department/i, 'Engineering')
    await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Create Team' }))

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn()
    render(<TeamFormDialog open team={null} onClose={onClose} onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('edit mode', () => {
  const existingTeam = {
    id: 't1',
    name: 'Platform Engineering',
    description: 'Owns the platform',
    department_id: 'dept-1',
    department_name: 'Engineering',
    manager_id: 'user-1',
    manager_name: 'Ada Lovelace',
    is_active: true,
  }

  it('renders the edit title and pre-fills every field', async () => {
    render(<TeamFormDialog open team={existingTeam} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByText('Edit Platform Engineering')).toBeInTheDocument()
    expect(screen.getByLabelText(/^name/i)).toHaveValue('Platform Engineering')
    expect(screen.getByLabelText(/description/i)).toHaveValue('Owns the platform')
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    expect(screen.getByRole('combobox', { name: /department/i })).toHaveTextContent('Engineering')
    expect(screen.getByRole('combobox', { name: /manager/i })).toHaveTextContent('Ada Lovelace')
  })

  it('submits only the changed shape expected by updateTeam', async () => {
    mockUpdateTeam.mockResolvedValue({ ...existingTeam, name: 'Renamed Team' })
    const onSaved = vi.fn()

    render(<TeamFormDialog open team={existingTeam} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())

    const nameField = screen.getByLabelText(/^name/i)
    await userEvent.clear(nameField)
    await userEvent.type(nameField, 'Renamed Team')
    await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() =>
      expect(mockUpdateTeam).toHaveBeenCalledWith('t1', {
        name: 'Renamed Team',
        description: 'Owns the platform',
        department_id: 'dept-1',
        manager_id: 'user-1',
        is_active: true,
      }),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('keeps an inactive-but-currently-assigned department selectable', async () => {
    const teamWithInactiveDept = { ...existingTeam, department_id: 'dept-9', department_name: 'Archived Dept' }
    render(<TeamFormDialog open team={teamWithInactiveDept} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    expect(screen.getByRole('combobox', { name: /department/i })).toHaveTextContent('Archived Dept (inactive)')
  })
})
