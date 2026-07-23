import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectFormDialog from './ProjectFormDialog'

const { MockApiError, mockCreateProject, mockUpdateProject, mockFetchDepartments, mockFetchUsers } = vi.hoisted(() => {
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
    mockCreateProject: vi.fn(),
    mockUpdateProject: vi.fn(),
    mockFetchDepartments: vi.fn(),
    mockFetchUsers: vi.fn(),
  }
})

vi.mock('../services/api', () => ({ ApiError: MockApiError }))
vi.mock('../services/directoryService', () => ({
  fetchDepartments: (...args) => mockFetchDepartments(...args),
  fetchUsers: (...args) => mockFetchUsers(...args),
}))
vi.mock('../services/projectService', () => ({
  createProject: (...args) => mockCreateProject(...args),
  updateProject: (...args) => mockUpdateProject(...args),
}))

const DEPARTMENTS = [{ id: 'dept-1', name: 'Finance' }]
const USERS = [{ id: 'user-1', full_name: 'Ada Lovelace', email: 'ada@example.com' }]

function renderDialog(props) {
  return render(
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <ProjectFormDialog {...props} />
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

function dateGroupSections(labelPattern) {
  const group = screen.getByRole('group', { name: labelPattern })
  return {
    year: within(group).getByRole('spinbutton', { name: 'Year' }),
    month: within(group).getByRole('spinbutton', { name: 'Month' }),
    day: within(group).getByRole('spinbutton', { name: 'Day' }),
  }
}

async function fillRequiredFieldsForCreate() {
  await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
  await userEvent.type(screen.getByLabelText(/code/i), 'PR05')
  await userEvent.type(screen.getByLabelText(/^name/i), 'New Project')
  await selectOption(/department/i, 'Finance')
  await selectOption(/manager/i, 'Ada Lovelace — ada@example.com')
  await pickDate(/start date/i, '2027-01-01')
  await pickDate(/planned end/i, '2027-06-30')
}

beforeEach(() => {
  mockCreateProject.mockReset()
  mockUpdateProject.mockReset()
  mockFetchDepartments.mockReset().mockResolvedValue(DEPARTMENTS)
  mockFetchUsers.mockReset().mockResolvedValue(USERS)
})

describe('create mode', () => {
  it('renders the create title with Status/Priority defaulted and submit disabled', async () => {
    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    expect(screen.getByRole('heading', { name: 'Create Project' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /^status/i })).toHaveTextContent('PLANNING')
    expect(screen.getByRole('combobox', { name: /^priority/i })).toHaveTextContent('MEDIUM')
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Create Project' })).toBeDisabled()
  })

  it('enables submit only once code, name, department, manager, and both dates are set', async () => {
    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    expect(screen.getByRole('button', { name: 'Create Project' })).toBeEnabled()
  })

  it('submits the expected payload, defaulting planned_budget to 0 and actual_end to null', async () => {
    const onSaved = vi.fn()
    const createdProject = { id: 'p1', code: 'PR05', name: 'New Project' }
    mockCreateProject.mockResolvedValue(createdProject)

    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))

    await waitFor(() =>
      expect(mockCreateProject).toHaveBeenCalledWith({
        code: 'PR05',
        name: 'New Project',
        description: null,
        department_id: 'dept-1',
        manager_id: 'user-1',
        status: 'PLANNING',
        priority: 'MEDIUM',
        start_date: '2027-01-01',
        planned_end: '2027-06-30',
        actual_end: null,
        planned_budget: 0,
      }),
    )
    expect(onSaved).toHaveBeenCalledWith(createdProject)
  })

  it('surfaces the COMPLETED/actual_end cross-field rule returned by the backend', async () => {
    mockCreateProject.mockRejectedValue(
      new MockApiError('One or more fields are invalid', {
        status: 400,
        details: { actual_end: 'is required when a project is marked completed' },
      }),
    )

    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await selectOption(/^status/i, 'COMPLETED')
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))

    expect(await screen.findByText('One or more fields are invalid')).toBeInTheDocument()
    expect(screen.getByText('is required when a project is marked completed')).toBeInTheDocument()
  })

  it('shows a generic message for a non-ApiError failure', async () => {
    mockCreateProject.mockRejectedValue(new Error('kaboom'))
    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument()
  })

  it('sends a numeric planned_budget when one is typed', async () => {
    mockCreateProject.mockResolvedValue({ id: 'p1' })
    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    const budgetField = screen.getByLabelText(/planned budget/i)
    await userEvent.clear(budgetField)
    await userEvent.type(budgetField, '25000')
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))

    await waitFor(() =>
      expect(mockCreateProject).toHaveBeenCalledWith(expect.objectContaining({ planned_budget: 25000 })),
    )
  })

  it('sets an optional Actual End date via the date picker', async () => {
    mockCreateProject.mockResolvedValue({ id: 'p1' })
    renderDialog({ open: true, project: null, onClose: vi.fn(), onSaved: vi.fn() })
    await fillRequiredFieldsForCreate()
    await pickDate(/actual end/i, '2027-07-04')
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }))

    await waitFor(() =>
      expect(mockCreateProject).toHaveBeenCalledWith(expect.objectContaining({ actual_end: '2027-07-04' })),
    )
  })
})

describe('edit mode', () => {
  const existingProject = {
    id: 'p1',
    code: 'PR03',
    name: 'Expense Tracker',
    description: null,
    department_id: 'dept-1',
    department_name: 'Finance',
    manager_id: 'user-1',
    manager_name: 'Ada Lovelace',
    status: 'ACTIVE',
    priority: 'HIGH',
    start_date: '2027-01-01',
    planned_end: '2027-06-30',
    actual_end: null,
    planned_budget: 5000,
  }

  it('renders the edit title and pre-fills every field including dates and budget', async () => {
    renderDialog({ open: true, project: existingProject, onClose: vi.fn(), onSaved: vi.fn() })
    expect(screen.getByRole('heading', { name: 'Edit Expense Tracker' })).toBeInTheDocument()
    expect(screen.getByLabelText(/code/i)).toHaveValue('PR03')
    expect(screen.getByLabelText(/planned budget/i)).toHaveValue(5000)

    const start = dateGroupSections(/start date/i)
    expect(start.year).toHaveTextContent('2027')
    expect(start.month).toHaveTextContent('01')
    expect(start.day).toHaveTextContent('01')

    const plannedEnd = dateGroupSections(/planned end/i)
    expect(plannedEnd.year).toHaveTextContent('2027')
    expect(plannedEnd.month).toHaveTextContent('06')
    expect(plannedEnd.day).toHaveTextContent('30')

    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    expect(screen.getByRole('combobox', { name: /^status/i })).toHaveTextContent('ACTIVE')
    expect(screen.getByRole('combobox', { name: /^priority/i })).toHaveTextContent('HIGH')
  })

  it('submits an update with the full current form state', async () => {
    mockUpdateProject.mockResolvedValue({ ...existingProject, priority: 'CRITICAL' })
    const onSaved = vi.fn()

    renderDialog({ open: true, project: existingProject, onClose: vi.fn(), onSaved })
    await waitFor(() => expect(mockFetchDepartments).toHaveBeenCalled())
    await selectOption(/^priority/i, 'CRITICAL')
    await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() =>
      expect(mockUpdateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ code: 'PR03', priority: 'CRITICAL', start_date: '2027-01-01', planned_end: '2027-06-30' }),
      ),
    )
    expect(onSaved).toHaveBeenCalled()
  })
})
