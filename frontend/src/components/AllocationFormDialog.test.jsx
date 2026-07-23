import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AllocationFormDialog from './AllocationFormDialog'

const { MockApiError, mockCreateAllocation, mockUpdateAllocation, mockFetchUsers, mockListProjects } = vi.hoisted(
  () => {
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
      mockCreateAllocation: vi.fn(),
      mockUpdateAllocation: vi.fn(),
      mockFetchUsers: vi.fn(),
      mockListProjects: vi.fn(),
    }
  },
)

vi.mock('../services/api', () => ({ ApiError: MockApiError }))
vi.mock('../services/allocationService', () => ({
  createAllocation: (...args) => mockCreateAllocation(...args),
  updateAllocation: (...args) => mockUpdateAllocation(...args),
}))
vi.mock('../services/directoryService', () => ({
  fetchUsers: (...args) => mockFetchUsers(...args),
}))
vi.mock('../services/projectService', () => ({
  listProjects: (...args) => mockListProjects(...args),
}))

const USERS = [{ id: 'user-1', full_name: 'Ada Lovelace', email: 'ada@example.com' }]
const PROJECTS = [{ id: 'proj-1', code: 'PR01', name: 'Expense Tracker' }]

function renderDialog(props) {
  return render(
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <AllocationFormDialog {...props} />
    </LocalizationProvider>,
  )
}

async function selectOption(labelPattern, optionText) {
  const combobox = screen.getByRole('combobox', { name: labelPattern })
  await userEvent.click(combobox)
  const listbox = await screen.findByRole('listbox')
  await userEvent.click(within(listbox).getByText(optionText))
}

// DesktopDatePicker splits its field into year/month/day spinbutton
// sections rather than a single native input — clicking the first section
// and typing the digits in order auto-advances through the rest.
async function pickDate(labelPattern, isoDateString) {
  const [year, month, day] = isoDateString.split('-')
  const group = screen.getByRole('group', { name: labelPattern })
  const sections = within(group).getAllByRole('spinbutton')
  await userEvent.click(sections[0])
  await userEvent.keyboard(year)
  await userEvent.keyboard(month)
  await userEvent.keyboard(day)
}

async function fillRequiredFieldsForCreate() {
  await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled())
  await selectOption(/^user/i, 'Ada Lovelace — ada@example.com')
  await selectOption(/^project/i, 'PR01 — Expense Tracker')
  await pickDate(/start date/i, '2027-01-01')
  await pickDate(/end date/i, '2027-03-01')
}

beforeEach(() => {
  mockCreateAllocation.mockReset()
  mockUpdateAllocation.mockReset()
  mockFetchUsers.mockReset().mockResolvedValue(USERS)
  mockListProjects.mockReset().mockResolvedValue({ projects: PROJECTS, meta: { total: 1 } })
})

describe('create mode', () => {
  it('renders the create title with a 50% default and submit disabled', async () => {
    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    expect(screen.getByRole('heading', { name: 'Create Allocation' })).toBeInTheDocument()
    expect(screen.getByLabelText(/allocation %/i)).toHaveValue(50)
    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Create Allocation' })).toBeDisabled()
  })

  it('enables submit once user, project, and both dates are set', async () => {
    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    expect(screen.getByRole('button', { name: 'Create Allocation' })).toBeEnabled()
  })

  it('submits the expected payload, defaulting role_on_project to null', async () => {
    const onSaved = vi.fn()
    const created = { id: 'a1' }
    mockCreateAllocation.mockResolvedValue(created)

    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Allocation' }))

    await waitFor(() =>
      expect(mockCreateAllocation).toHaveBeenCalledWith({
        user_id: 'user-1',
        project_id: 'proj-1',
        role_on_project: null,
        allocation_pct: 50,
        start_date: '2027-01-01',
        end_date: '2027-03-01',
      }),
    )
    expect(onSaved).toHaveBeenCalledWith(created)
  })

  it('surfaces an over-allocation conflict with the numeric breakdown in the banner', async () => {
    mockCreateAllocation.mockRejectedValue(
      new MockApiError('Allocation exceeds capacity', {
        status: 409,
        code: 'conflict',
        details: { existing_pct: 60, requested_pct: 50, projected_pct: 110, max_pct: 100 },
      }),
    )

    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Allocation' }))

    expect(
      await screen.findByText('Allocation exceeds capacity (existing 60% + requested 50% = 110%, max 100%)'),
    ).toBeInTheDocument()
  })

  it('surfaces a plain field-level error message when not a conflict', async () => {
    mockCreateAllocation.mockRejectedValue(
      new MockApiError('One or more fields are invalid', {
        status: 400,
        details: { start_date: 'must be before end_date' },
      }),
    )

    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Allocation' }))

    expect(await screen.findByText('One or more fields are invalid')).toBeInTheDocument()
    expect(screen.getByText('must be before end_date')).toBeInTheDocument()
  })

  it('shows a generic message for a non-ApiError failure', async () => {
    mockCreateAllocation.mockRejectedValue(new Error('kaboom'))
    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Allocation' }))
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
  })

  it('shows a warning when the dropdown options fail to load', async () => {
    mockFetchUsers.mockRejectedValue(new MockApiError('Network error', { status: 0 }))
    renderDialog({ open: true, allocation: null, onClose: vi.fn(), onSaved: vi.fn() })
    expect(await screen.findByText('Network error')).toBeInTheDocument()
  })
})

describe('edit mode', () => {
  const existingAllocation = {
    id: 'a1',
    user_id: 'user-1',
    user_name: 'Ada Lovelace',
    project_id: 'proj-1',
    project_code: 'PR01',
    project_name: 'Expense Tracker',
    role_on_project: 'Tech Lead',
    allocation_pct: 75,
    start_date: '2027-01-01',
    end_date: '2027-03-01',
  }

  it('renders the edit title and pre-fills every field', async () => {
    renderDialog({ open: true, allocation: existingAllocation, onClose: vi.fn(), onSaved: vi.fn() })
    expect(screen.getByRole('heading', { name: 'Edit Allocation' })).toBeInTheDocument()
    expect(screen.getByLabelText(/role on project/i)).toHaveValue('Tech Lead')
    expect(screen.getByLabelText(/allocation %/i)).toHaveValue(75)

    const start = screen.getByRole('group', { name: /start date/i })
    expect(within(start).getByRole('spinbutton', { name: 'Year' })).toHaveTextContent('2027')
    expect(within(start).getByRole('spinbutton', { name: 'Month' })).toHaveTextContent('01')
    expect(within(start).getByRole('spinbutton', { name: 'Day' })).toHaveTextContent('01')

    const end = screen.getByRole('group', { name: /end date/i })
    expect(within(end).getByRole('spinbutton', { name: 'Year' })).toHaveTextContent('2027')
    expect(within(end).getByRole('spinbutton', { name: 'Month' })).toHaveTextContent('03')
    expect(within(end).getByRole('spinbutton', { name: 'Day' })).toHaveTextContent('01')
  })

  it('submits an update via updateAllocation', async () => {
    mockUpdateAllocation.mockResolvedValue({ ...existingAllocation, allocation_pct: 90 })
    const onSaved = vi.fn()

    renderDialog({ open: true, allocation: existingAllocation, onClose: vi.fn(), onSaved })
    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled())

    const pctField = screen.getByLabelText(/allocation %/i)
    await userEvent.clear(pctField)
    await userEvent.type(pctField, '90')
    await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() =>
      expect(mockUpdateAllocation).toHaveBeenCalledWith(
        'a1',
        expect.objectContaining({ allocation_pct: 90, start_date: '2027-01-01', end_date: '2027-03-01' }),
      ),
    )
    expect(onSaved).toHaveBeenCalled()
  })

  it('keeps a user/project no longer in the options list selectable and labelled inactive', async () => {
    mockFetchUsers.mockResolvedValue([])
    mockListProjects.mockResolvedValue({ projects: [], meta: { total: 0 } })

    renderDialog({ open: true, allocation: existingAllocation, onClose: vi.fn(), onSaved: vi.fn() })
    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalled())

    expect(screen.getByRole('combobox', { name: /^user/i })).toHaveTextContent('Ada Lovelace (inactive)')
    expect(screen.getByRole('combobox', { name: /^project/i })).toHaveTextContent(
      'PR01 — Expense Tracker (inactive)',
    )
  })
})
