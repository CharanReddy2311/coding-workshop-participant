import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Teams from './Teams'

// Teams.jsx always renders <TeamFormDialog> and <AppLayout> as children —
// even with the dialog closed, TeamFormDialog's own effect still fires and
// calls fetchDepartments/fetchUsers, and AppLayout calls useAuth() for the
// nav bar — so both need mocking here too, not just what Teams.jsx itself
// imports directly.
const {
  mockUseAuth,
  mockListTeams,
  mockDeleteTeam,
  mockCreateTeam,
  mockUpdateTeam,
  mockFetchDepartments,
  mockFetchUsers,
} = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockListTeams: vi.fn(),
  mockDeleteTeam: vi.fn(),
  mockCreateTeam: vi.fn(),
  mockUpdateTeam: vi.fn(),
  mockFetchDepartments: vi.fn(),
  mockFetchUsers: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../services/teamService', () => ({
  listTeams: (...args) => mockListTeams(...args),
  deleteTeam: (...args) => mockDeleteTeam(...args),
  createTeam: (...args) => mockCreateTeam(...args),
  updateTeam: (...args) => mockUpdateTeam(...args),
  fetchDepartments: (...args) => mockFetchDepartments(...args),
  fetchUsers: (...args) => mockFetchUsers(...args),
}))

const SAMPLE_TEAMS = [
  {
    id: 't1',
    name: 'Platform Engineering',
    description: 'Owns the platform',
    department_name: 'Engineering',
    manager_name: 'Ada Lovelace',
    is_active: true,
  },
  {
    id: 't2',
    name: 'Retired Team',
    description: null,
    department_name: 'Finance',
    manager_name: 'Grace Hopper',
    is_active: false,
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

function renderTeams() {
  return render(
    <MemoryRouter>
      <Teams />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockListTeams.mockReset()
  mockDeleteTeam.mockReset()
  mockCreateTeam.mockReset()
  mockUpdateTeam.mockReset()
  mockFetchDepartments.mockReset().mockResolvedValue([])
  mockFetchUsers.mockReset().mockResolvedValue([])
  // Teams.jsx fires two listTeams calls on mount: one for the department
  // filter options (limit 200), one for the actual paginated table.
  mockListTeams.mockResolvedValue({ teams: SAMPLE_TEAMS, meta: { total: 2, limit: 10, offset: 0 } })
  authAs('ADMIN')
})

describe('list rendering', () => {
  it('renders every team with its department, manager, and status', async () => {
    renderTeams()

    expect(await screen.findByText('Platform Engineering')).toBeInTheDocument()
    expect(screen.getByText('Owns the platform')).toBeInTheDocument()
    expect(screen.getByText('Engineering')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()

    expect(screen.getByText('Retired Team')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('shows an empty state when there are no teams', async () => {
    mockListTeams.mockResolvedValue({ teams: [], meta: { total: 0, limit: 10, offset: 0 } })
    renderTeams()
    expect(await screen.findByText('No teams found.')).toBeInTheDocument()
  })

  it('shows an error alert when the list request fails', async () => {
    mockListTeams.mockRejectedValue(new Error('Failed to load teams'))
    renderTeams()
    expect(await screen.findByText('Failed to load teams')).toBeInTheDocument()
  })

  it('reflects the total count in the pagination control', async () => {
    mockListTeams.mockResolvedValue({ teams: SAMPLE_TEAMS, meta: { total: 47, limit: 10, offset: 0 } })
    renderTeams()
    await screen.findByText('Platform Engineering')
    // MUI splits this text across nested elements, so a single getByText
    // can't match it as one text node — check the rendered text directly.
    // The range reflects rowsPerPage (10), not the actual rows returned.
    expect(document.body.textContent).toContain('1–10 of 47')
  })

  it('debounces search input into a q parameter', async () => {
    renderTeams()
    await screen.findByText('Platform Engineering')
    mockListTeams.mockClear()

    await userEvent.type(screen.getByLabelText(/search by name/i), 'platform')

    await waitFor(
      () =>
        expect(mockListTeams).toHaveBeenCalledWith(expect.objectContaining({ q: 'platform' })),
      { timeout: 2000 },
    )
  })
})

describe('RBAC-gated actions', () => {
  it('disables Create, Edit, and Delete for a Viewer', async () => {
    authAs('VIEWER')
    renderTeams()
    await screen.findByText('Platform Engineering')

    expect(screen.getByRole('button', { name: /create team/i })).toBeDisabled()
    const rows = screen.getAllByRole('row').slice(1) // skip header row
    within(rows[0])
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeDisabled())
  })

  it('allows editing but not creating or deleting for a Contributor', async () => {
    authAs('CONTRIBUTOR')
    renderTeams()
    await screen.findByText('Platform Engineering')

    expect(screen.getByRole('button', { name: /create team/i })).toBeDisabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [editButton, deleteButton] = within(firstRow).getAllByRole('button')
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeDisabled()
  })

  it('allows creating and editing but not deleting for a Manager', async () => {
    authAs('MANAGER')
    renderTeams()
    await screen.findByText('Platform Engineering')

    expect(screen.getByRole('button', { name: /create team/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    const [editButton, deleteButton] = within(firstRow).getAllByRole('button')
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeDisabled()
  })

  it('enables every action for an Admin', async () => {
    authAs('ADMIN')
    renderTeams()
    await screen.findByText('Platform Engineering')

    expect(screen.getByRole('button', { name: /create team/i })).toBeEnabled()
    const firstRow = screen.getAllByRole('row')[1]
    within(firstRow)
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeEnabled())
  })
})

describe('delete flow', () => {
  it('confirms before deleting, then removes the team and shows a snackbar', async () => {
    authAs('ADMIN')
    renderTeams()
    await screen.findByText('Platform Engineering')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    expect(await screen.findByText('Delete team?')).toBeInTheDocument()

    mockDeleteTeam.mockResolvedValue(undefined)
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mockDeleteTeam).toHaveBeenCalledWith('t1'))
    expect(await screen.findByText('Team "Platform Engineering" deleted')).toBeInTheDocument()
  })

  it('shows the backend error inside the confirm dialog when delete fails', async () => {
    authAs('ADMIN')
    renderTeams()
    await screen.findByText('Platform Engineering')

    const firstRow = screen.getAllByRole('row')[1]
    const [, deleteButton] = within(firstRow).getAllByRole('button')
    await userEvent.click(deleteButton)

    mockDeleteTeam.mockRejectedValue(new Error('Failed to delete team'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Failed to delete team')).toBeInTheDocument()
  })
})
