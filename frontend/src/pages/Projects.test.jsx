import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Projects from './Projects'

// Like Teams.jsx, Projects.jsx unconditionally renders <ProjectFormDialog>
// (its effect still fires fetchDepartments/fetchUsers even closed) and
// <AppLayout> (needs useAuth()) — both need mocking, not just what
// Projects.jsx itself imports directly.
const {
  mockUseAuth,
  mockListProjects,
  mockDeleteProject,
  mockCreateProject,
  mockUpdateProject,
  mockFetchDepartments,
  mockFetchUsers,
} = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockListProjects: vi.fn(),
  mockDeleteProject: vi.fn(),
  mockCreateProject: vi.fn(),
  mockUpdateProject: vi.fn(),
  mockFetchDepartments: vi.fn(),
  mockFetchUsers: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../services/projectService', () => ({
  listProjects: (...args) => mockListProjects(...args),
  deleteProject: (...args) => mockDeleteProject(...args),
  createProject: (...args) => mockCreateProject(...args),
  updateProject: (...args) => mockUpdateProject(...args),
}))
vi.mock('../services/directoryService', () => ({
  fetchDepartments: (...args) => mockFetchDepartments(...args),
  fetchUsers: (...args) => mockFetchUsers(...args),
}))

const SAMPLE_PROJECTS = [
  {
    id: 'p1',
    code: 'PR01',
    name: 'Expense Tracker',
    description: 'Internal tool',
    department_name: 'Finance',
    manager_name: 'Ada Lovelace',
    status: 'ACTIVE',
    priority: 'HIGH',
    planned_end: '2099-01-01',
    planned_budget: 5000,
  },
  {
    id: 'p2',
    code: 'PR02',
    name: 'Overdue Thing',
    description: null,
    department_name: 'Engineering',
    manager_name: 'Grace Hopper',
    status: 'ON_HOLD',
    priority: 'LOW',
    planned_end: '2000-01-01',
    planned_budget: 0,
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

function renderProjects() {
  return render(
    <MemoryRouter>
      <Projects />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockListProjects.mockReset()
  mockDeleteProject.mockReset()
  mockCreateProject.mockReset()
  mockUpdateProject.mockReset()
  mockFetchDepartments.mockReset().mockResolvedValue([])
  mockFetchUsers.mockReset().mockResolvedValue([])
  mockListProjects.mockResolvedValue({ projects: SAMPLE_PROJECTS, meta: { total: 2, limit: 10, offset: 0 } })
  authAs('ADMIN')
})

describe('list rendering', () => {
  it('renders every project with its department, manager, status, priority, and budget', async () => {
    renderProjects()

    expect(await screen.findByText('PR01 — Expense Tracker')).toBeInTheDocument()
    expect(screen.getByText('Internal tool')).toBeInTheDocument()
    expect(screen.getByText('Finance')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByText('$5,000')).toBeInTheDocument()
  })

  it('flags a planned_end in the past on an open project as overdue', async () => {
    renderProjects()
    expect(await screen.findByText('2000-01-01 (overdue)')).toBeInTheDocument()
  })

  it('shows an empty state when there are no projects', async () => {
    mockListProjects.mockResolvedValue({ projects: [], meta: { total: 0, limit: 10, offset: 0 } })
    renderProjects()
    expect(await screen.findByText('No projects found.')).toBeInTheDocument()
  })

  it('shows an error alert when the list request fails', async () => {
    mockListProjects.mockRejectedValue(new Error('Failed to load projects'))
    renderProjects()
    expect(await screen.findByText('Failed to load projects')).toBeInTheDocument()
  })

  it('debounces search input into a q parameter', async () => {
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')
    mockListProjects.mockClear()

    await userEvent.type(screen.getByLabelText(/search by name/i), 'expense')

    await waitFor(
      () => expect(mockListProjects).toHaveBeenCalledWith(expect.objectContaining({ q: 'expense' })),
      { timeout: 2000 },
    )
  })

  it('filters by status', async () => {
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')
    mockListProjects.mockClear()

    await userEvent.click(screen.getByRole('combobox', { name: /status/i }))
    await userEvent.click(within(await screen.findByRole('listbox')).getByText('ON_HOLD'.replace('_', ' ')))

    await waitFor(() =>
      expect(mockListProjects).toHaveBeenCalledWith(expect.objectContaining({ status: 'ON_HOLD' })),
    )
  })
})

describe('RBAC-gated actions', () => {
  it('disables Create for a Contributor but allows editing', async () => {
    authAs('CONTRIBUTOR')
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')

    expect(screen.getByRole('button', { name: /create project/i })).toBeDisabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [editButton, deleteButton] = within(firstRow).getAllByRole('button')
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeDisabled()
  })

  it('enables Create for a Manager but not Delete', async () => {
    authAs('MANAGER')
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')

    expect(screen.getByRole('button', { name: /create project/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    expect(deleteButton).toBeDisabled()
  })

  it('enables every action for an Admin', async () => {
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')

    expect(screen.getByRole('button', { name: /create project/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    within(firstRow)
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeEnabled())
  })
})

describe('delete flow', () => {
  it('confirms before deleting, then removes the project and shows a snackbar', async () => {
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    expect(await screen.findByText('Delete project?')).toBeInTheDocument()

    mockDeleteProject.mockResolvedValue(undefined)
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mockDeleteProject).toHaveBeenCalledWith('p1'))
    expect(await screen.findByText('Project "Expense Tracker" deleted')).toBeInTheDocument()
  })

  it('surfaces the backend hint alongside the error message when delete fails', async () => {
    renderProjects()
    await screen.findByText('PR01 — Expense Tracker')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    const err = new Error('Cannot delete project')
    err.details = { hint: 'Remove its deliverables first.' }
    mockDeleteProject.mockRejectedValue(err)
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Cannot delete project Remove its deliverables first.')).toBeInTheDocument()
  })
})
