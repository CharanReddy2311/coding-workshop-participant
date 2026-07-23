import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'

const { mockUseAuth, mockListProjects, mockListDeliverables, mockListAllocations } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
  mockListProjects: vi.fn(),
  mockListDeliverables: vi.fn(),
  mockListAllocations: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }))
vi.mock('../services/projectService', () => ({ listProjects: (...args) => mockListProjects(...args) }))
vi.mock('../services/deliverableService', () => ({ listDeliverables: (...args) => mockListDeliverables(...args) }))
vi.mock('../services/allocationService', () => ({ listAllocations: (...args) => mockListAllocations(...args) }))

// recharts renders to SVG sized via ResizeObserver, neither of which jsdom
// implements — the standard approach is to swap in lightweight stand-ins
// that surface the *data* each chart receives as plain text/DOM, so tests
// verify our data transformations rather than fighting recharts internals.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  PieChart: ({ children }) => <div>{children}</div>,
  Pie: ({ data = [] }) => (
    <div data-testid="pie">
      {data.map((d) => (
        <div key={d.name}>{`${d.name}: ${d.value}`}</div>
      ))}
    </div>
  ),
  BarChart: ({ data = [], children }) => (
    <div>
      <div data-testid="bar-chart-data">{JSON.stringify(data)}</div>
      {children}
    </div>
  ),
  Bar: ({ dataKey, name }) => (
    <div data-testid="bar" data-key={dataKey}>
      {name || dataKey}
    </div>
  ),
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Legend: () => null,
  Tooltip: () => null,
  ReferenceLine: ({ label }) => <div data-testid="reference-line">{label?.value}</div>,
}))

const pastDate = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
const futureDate = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)

const PROJECTS = [
  {
    id: 'p1',
    code: 'PR01',
    name: 'On Track Project',
    department_name: 'Engineering',
    manager_name: 'Grace Hopper',
    status: 'ACTIVE',
    planned_end: futureDate,
    planned_budget: 10000,
  },
  {
    id: 'p2',
    code: 'PR02',
    name: 'Overdue Project',
    department_name: 'Finance',
    manager_name: 'Katherine Johnson',
    status: 'ACTIVE',
    planned_end: pastDate,
    planned_budget: 20000,
  },
  {
    id: 'p3',
    code: 'PR03',
    name: 'Completed Project',
    department_name: 'Product',
    manager_name: 'Ada Lovelace',
    status: 'COMPLETED',
    planned_end: pastDate,
    planned_budget: 5000,
  },
]

const DELIVERABLES = [
  { id: 'd1', project_id: 'p1', status: 'IN_PROGRESS', percent_complete: 50, weight: 1 },
  { id: 'd2', project_id: 'p1', status: 'COMPLETED', percent_complete: 100, weight: 1 },
  // p2 (Overdue Project) intentionally has zero deliverables.
]

const ALLOCATIONS = [
  { id: 'a1', user_id: 'u1', user_name: 'Alan Turing', project_name: 'On Track Project', allocation_pct: 70, start_date: pastDate, end_date: futureDate },
  { id: 'a2', user_id: 'u1', user_name: 'Alan Turing', project_name: 'Overdue Project', allocation_pct: 60, start_date: pastDate, end_date: futureDate },
  { id: 'a3', user_id: 'u2', user_name: 'Margaret Hamilton', project_name: 'On Track Project', allocation_pct: 40, start_date: pastDate, end_date: futureDate },
]

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

function barChartDataFor(widgetTitle) {
  const card = screen.getByText(widgetTitle).closest('.MuiCard-root')
  const raw = within(card).getByTestId('bar-chart-data').textContent
  return JSON.parse(raw)
}

beforeEach(() => {
  mockUseAuth.mockReset().mockReturnValue({
    user: { id: 'u1', full_name: 'Test User', email: 'test@example.com', role: 'ADMIN' },
    logout: vi.fn(),
    hasRole: () => true,
  })
  mockListProjects.mockReset().mockResolvedValue({ projects: PROJECTS, meta: { total: PROJECTS.length } })
  mockListDeliverables.mockReset().mockResolvedValue({ deliverables: DELIVERABLES, meta: { total: DELIVERABLES.length } })
  mockListAllocations.mockReset().mockResolvedValue({ allocations: ALLOCATIONS, meta: { total: ALLOCATIONS.length } })
})

it('greets the logged-in user by name and role', async () => {
  renderDashboard()
  expect(await screen.findByText('Welcome, Test User')).toBeInTheDocument()
  expect(screen.getByText(/logged in as admin/i)).toBeInTheDocument()
})

it('shows an error alert when any data source fails to load', async () => {
  mockListProjects.mockRejectedValue(new Error('Failed to load dashboard data'))
  renderDashboard()
  expect(await screen.findByText('Failed to load dashboard data')).toBeInTheDocument()
})

describe('KPI row', () => {
  it('counts active projects, at-risk projects, over-allocated people, and completed deliverables', async () => {
    renderDashboard()
    await screen.findByText('Welcome, Test User')

    expect(screen.getByText('Active Projects').parentElement).toHaveTextContent('2Active Projects')
    // "At-Risk Projects" is both a KPI tile label and the widget title below
    // it — the KPI tile renders first in the DOM.
    expect(screen.getAllByText('At-Risk Projects')[0].parentElement).toHaveTextContent('1At-Risk Projects')
    // Alan Turing is the only one over 100% (70% + 60% = 130%).
    expect(screen.getByText('Over-Allocated People').parentElement).toHaveTextContent('1Over-Allocated People')
    // 1 of 2 deliverables is COMPLETED.
    expect(screen.getByText('Deliverables Completed').parentElement).toHaveTextContent('50%Deliverables Completed')
  })
})

describe('Project Health', () => {
  it('renders a pie slice with the right count for each status present', async () => {
    renderDashboard()
    expect(await screen.findByText('ACTIVE: 2')).toBeInTheDocument()
    expect(screen.getByText('COMPLETED: 1')).toBeInTheDocument()
  })

  it('shows a clear message when there are no projects', async () => {
    mockListProjects.mockResolvedValue({ projects: [], meta: { total: 0 } })
    renderDashboard()
    expect(await screen.findByText('No projects yet.')).toBeInTheDocument()
  })
})

describe('At-Risk Projects', () => {
  // PR02 is ACTIVE (and overdue), so it also appears in the separate
  // Budget vs Planned widget — every lookup here is scoped to the
  // At-Risk Projects card specifically.
  function atRiskCard() {
    return screen.getAllByText('At-Risk Projects')[1].closest('.MuiCard-root')
  }

  it('flags the overdue project and the project with zero deliverables as the same at-risk entry', async () => {
    renderDashboard()
    await screen.findByText('Active Projects')
    const card = within(atRiskCard())
    expect(card.getByText('PR02 — Overdue Project')).toBeInTheDocument()
    expect(card.getByText('Overdue')).toBeInTheDocument()
    expect(card.getByText('No deliverables')).toBeInTheDocument()
  })

  it('does not flag the on-track project', async () => {
    renderDashboard()
    await screen.findByText('Active Projects')
    const card = within(atRiskCard())
    expect(card.queryByText('PR01 — On Track Project')).not.toBeInTheDocument()
  })

  it('shows a clear message when nothing is at risk', async () => {
    mockListProjects.mockResolvedValue({
      projects: [PROJECTS[0]],
      meta: { total: 1 },
    })
    renderDashboard()
    expect(await screen.findByText('No open projects are currently at risk.')).toBeInTheDocument()
  })
})

describe('Resource Allocation', () => {
  it('charts every person active today with their total allocation percentage', async () => {
    renderDashboard()
    await screen.findByText('Resource Allocation')

    const data = barChartDataFor('Resource Allocation')
    expect(data).toEqual([
      { name: 'Alan Turing', total: 130 },
      { name: 'Margaret Hamilton', total: 40 },
    ])
  })

  it('renders a 100% capacity reference line', async () => {
    renderDashboard()
    expect(await screen.findByText('100% Capacity')).toBeInTheDocument()
  })

  it('shows a clear message when nobody has an active allocation', async () => {
    mockListAllocations.mockResolvedValue({ allocations: [], meta: { total: 0 } })
    renderDashboard()
    expect(await screen.findByText('No active allocations today.')).toBeInTheDocument()
  })
})

describe('Budget vs Planned', () => {
  it('estimates consumption from weighted deliverable progress for active projects', async () => {
    renderDashboard()
    // On Track Project: deliverables weighted 50% and 100% at weight 1 each -> 75% estimate.
    expect(await screen.findByText('PR01 — On Track Project')).toBeInTheDocument()
    expect(screen.getByText(/75%/)).toBeInTheDocument()
  })

  it('does not include the completed project', async () => {
    renderDashboard()
    await screen.findByText('PR01 — On Track Project')
    expect(screen.queryByText('PR03 — Completed Project')).not.toBeInTheDocument()
  })
})

describe('Deliverables Progress', () => {
  it('stacks deliverable counts by status for each project that has any', async () => {
    renderDashboard()
    await screen.findByText('Deliverables Progress')

    const data = barChartDataFor('Deliverables Progress')
    expect(data).toEqual([
      { project: 'PR01', NOT_STARTED: 0, IN_PROGRESS: 1, BLOCKED: 0, COMPLETED: 1, CANCELLED: 0 },
    ])
  })

  it('renders one stacked bar segment per deliverable status', async () => {
    renderDashboard()
    await screen.findByText('Deliverables Progress')
    // Scoped to this card — the Resource Allocation chart on the same page
    // renders its own <Bar> too.
    const card = screen.getByText('Deliverables Progress').closest('.MuiCard-root')
    const bars = within(card).getAllByTestId('bar')
    const keys = bars.map((bar) => bar.getAttribute('data-key'))
    expect(keys).toEqual(['NOT_STARTED', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED'])
  })

  it('shows a clear message when there are no deliverables', async () => {
    mockListDeliverables.mockResolvedValue({ deliverables: [], meta: { total: 0 } })
    renderDashboard()
    expect(await screen.findByText('No deliverables yet.')).toBeInTheDocument()
  })
})
