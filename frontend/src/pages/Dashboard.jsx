import { useEffect, useMemo, useState } from 'react'
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineRounded'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import PersonOffIcon from '@mui/icons-material/PersonOff'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import {
  Alert,
  Avatar,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'

import AppLayout from '../components/AppLayout'
import { useAuth } from '../context/AuthContext'
import { listAllocations } from '../services/allocationService'
import { listDeliverables } from '../services/deliverableService'
import { listProjects } from '../services/projectService'

const OPEN_PROJECT_STATUSES = ['PLANNING', 'ACTIVE', 'ON_HOLD']

const PROJECT_STATUS_COLORS = {
  PLANNING: '#8a94a6',
  ACTIVE: '#2f6f9e',
  ON_HOLD: '#c98a1e',
  COMPLETED: '#2e9e6b',
  CANCELLED: '#c0392b',
}

const DELIVERABLE_STATUS_COLORS = {
  NOT_STARTED: '#8a94a6',
  IN_PROGRESS: '#2f6f9e',
  BLOCKED: '#c98a1e',
  COMPLETED: '#2e9e6b',
  CANCELLED: '#c0392b',
}

const today = new Date().toISOString().slice(0, 10)

function isProjectOverdue(project) {
  return OPEN_PROJECT_STATUSES.includes(project.status) && project.planned_end < today
}

function isAllocationActiveToday(allocation) {
  return allocation.start_date <= today && today <= allocation.end_date
}

/** Small rounded stat tile used across the top KPI row. */
function StatTile({ icon, label, value, color }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
          <Avatar sx={{ bgcolor: `${color}1a`, color, width: 44, height: 44 }}>{icon}</Avatar>
          <Box>
            <Typography variant="h5" fontWeight={700}>
              {value}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {label}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

function WidgetCard({ title, subtitle, children }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
            {subtitle}
          </Typography>
        )}
        {children}
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const { user } = useAuth()

  const [projects, setProjects] = useState([])
  const [deliverables, setDeliverables] = useState([])
  const [allocations, setAllocations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const [projectsRes, deliverablesRes, allocationsRes] = await Promise.all([
          listProjects({ limit: 200, sort: 'name', order: 'asc' }),
          listDeliverables({ limit: 500 }),
          listAllocations({ limit: 500 }),
        ])
        if (cancelled) return
        setProjects(projectsRes.projects)
        setDeliverables(deliverablesRes.deliverables)
        setAllocations(allocationsRes.allocations)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load dashboard data')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const projectStatusCounts = useMemo(() => {
    const counts = { PLANNING: 0, ACTIVE: 0, ON_HOLD: 0, COMPLETED: 0, CANCELLED: 0 }
    projects.forEach((p) => {
      if (counts[p.status] !== undefined) counts[p.status] += 1
    })
    return counts
  }, [projects])

  const projectHealthChartData = useMemo(
    () =>
      Object.entries(projectStatusCounts)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => ({
          status,
          name: status.replace(/_/g, ' '),
          value: count,
          color: PROJECT_STATUS_COLORS[status],
        })),
    [projectStatusCounts],
  )

  const deliverablesByProject = useMemo(() => {
    const map = new Map()
    deliverables.forEach((d) => {
      if (!map.has(d.project_id)) map.set(d.project_id, [])
      map.get(d.project_id).push(d)
    })
    return map
  }, [deliverables])

  const atRiskProjects = useMemo(() => {
    return projects
      .filter((p) => OPEN_PROJECT_STATUSES.includes(p.status))
      .map((p) => {
        const projectDeliverables = deliverablesByProject.get(p.id) || []
        const reasons = []
        if (isProjectOverdue(p)) reasons.push('Overdue')
        if (projectDeliverables.length === 0) reasons.push('No deliverables')
        return { project: p, reasons }
      })
      .filter((entry) => entry.reasons.length > 0)
  }, [projects, deliverablesByProject])

  // Every person with an allocation active today, not just the
  // over-allocated ones — the chart's 100% reference line is what makes
  // over-allocation pop out visually.
  const allocationByUser = useMemo(() => {
    const byUser = new Map()
    allocations.filter(isAllocationActiveToday).forEach((a) => {
      if (!byUser.has(a.user_id)) byUser.set(a.user_id, { name: a.user_name, total: 0 })
      byUser.get(a.user_id).total += a.allocation_pct
    })
    return [...byUser.values()].sort((a, b) => b.total - a.total)
  }, [allocations])

  const overAllocatedCount = useMemo(
    () => allocationByUser.filter((entry) => entry.total > 100).length,
    [allocationByUser],
  )

  const activeProjectsWithProgress = useMemo(() => {
    return projects
      .filter((p) => p.status === 'ACTIVE')
      .map((p) => {
        const projectDeliverables = deliverablesByProject.get(p.id) || []
        const totalWeight = projectDeliverables.reduce((sum, d) => sum + (Number(d.weight) || 0), 0)
        const weightedComplete = projectDeliverables.reduce(
          (sum, d) => sum + (Number(d.weight) || 0) * (Number(d.percent_complete) || 0),
          0,
        )
        const estimatedPct = totalWeight > 0 ? Math.round(weightedComplete / totalWeight) : 0
        return { project: p, estimatedPct }
      })
  }, [projects, deliverablesByProject])

  const deliverableStatusCounts = useMemo(() => {
    const counts = { NOT_STARTED: 0, IN_PROGRESS: 0, BLOCKED: 0, COMPLETED: 0, CANCELLED: 0 }
    deliverables.forEach((d) => {
      if (counts[d.status] !== undefined) counts[d.status] += 1
    })
    return counts
  }, [deliverables])

  // Per-project breakdown for the Deliverables Progress stacked bar chart —
  // shows where each project's deliverables are bottlenecked, not just the
  // portfolio-wide total.
  const deliverablesByProjectChartData = useMemo(() => {
    const rows = []
    deliverablesByProject.forEach((projectDeliverables, projectId) => {
      const project = projects.find((p) => p.id === projectId)
      if (!project) return
      const counts = { NOT_STARTED: 0, IN_PROGRESS: 0, BLOCKED: 0, COMPLETED: 0, CANCELLED: 0 }
      projectDeliverables.forEach((d) => {
        if (counts[d.status] !== undefined) counts[d.status] += 1
      })
      rows.push({ project: project.code, ...counts })
    })
    return rows
  }, [deliverablesByProject, projects])

  const totalProjects = projects.length
  const totalDeliverables = deliverables.length
  const completedDeliverablesPct =
    totalDeliverables > 0 ? Math.round((deliverableStatusCounts.COMPLETED / totalDeliverables) * 100) : 0

  return (
    <AppLayout>
      <Box sx={{ maxWidth: 1400, mx: 'auto', p: { xs: 2, sm: 3 } }}>
        <Typography variant="h5" gutterBottom>
          Welcome, {user.full_name}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Command center for ACME Inc.&apos;s active project portfolio — logged in as {user.role.toLowerCase()}.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : (
          <Stack spacing={3}>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <StatTile
                  icon={<FolderOpenIcon />}
                  label="Active Projects"
                  value={projectStatusCounts.ACTIVE}
                  color="#2f6f9e"
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <StatTile
                  icon={<WarningAmberIcon />}
                  label="At-Risk Projects"
                  value={atRiskProjects.length}
                  color="#c98a1e"
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <StatTile
                  icon={<PersonOffIcon />}
                  label="Over-Allocated People"
                  value={overAllocatedCount}
                  color="#c0392b"
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <StatTile
                  icon={<AssignmentTurnedInIcon />}
                  label="Deliverables Completed"
                  value={`${completedDeliverablesPct}%`}
                  color="#2e9e6b"
                />
              </Grid>
            </Grid>

            <Grid container spacing={2}>
              {/* 1. Project Health — donut chart of projects by status */}
              <Grid size={{ xs: 12, md: 5 }}>
                <WidgetCard title="Project Health" subtitle={`${totalProjects} projects across the portfolio`}>
                  {projectHealthChartData.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No projects yet.
                    </Typography>
                  ) : (
                    <Box sx={{ width: '100%', height: 280 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={projectHealthChartData}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={58}
                            outerRadius={95}
                            paddingAngle={2}
                          >
                            {projectHealthChartData.map((entry) => (
                              <Cell key={entry.status} fill={entry.color} />
                            ))}
                          </Pie>
                          <RechartsTooltip formatter={(value, name) => [`${value} project${value === 1 ? '' : 's'}`, name]} />
                          <Legend verticalAlign="bottom" height={36} iconType="circle" />
                        </PieChart>
                      </ResponsiveContainer>
                    </Box>
                  )}
                </WidgetCard>
              </Grid>

              {/* 3. Resource Allocation — bar chart with a 100% capacity reference line */}
              <Grid size={{ xs: 12, md: 7 }}>
                <WidgetCard
                  title="Resource Allocation"
                  subtitle="Total allocation % per person, active today — bars above the line are over capacity"
                >
                  {allocationByUser.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No active allocations today.
                    </Typography>
                  ) : (
                    <Box sx={{ width: '100%', height: 280 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={allocationByUser} margin={{ top: 8, right: 16, left: 0, bottom: 32 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis
                            dataKey="name"
                            angle={-30}
                            textAnchor="end"
                            interval={0}
                            height={60}
                            tick={{ fontSize: 12 }}
                          />
                          <YAxis unit="%" tick={{ fontSize: 12 }} />
                          <RechartsTooltip formatter={(value) => [`${value}%`, 'Allocated']} />
                          <ReferenceLine
                            y={100}
                            stroke="#c0392b"
                            strokeDasharray="4 4"
                            label={{ value: '100% Capacity', position: 'insideTopRight', fill: '#c0392b', fontSize: 12 }}
                          />
                          <Bar dataKey="total" name="Allocation" radius={[4, 4, 0, 0]}>
                            {allocationByUser.map((entry) => (
                              <Cell key={entry.name} fill={entry.total > 100 ? '#c0392b' : '#2f6f9e'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </Box>
                  )}
                </WidgetCard>
              </Grid>

              {/* 2. At-Risk Projects */}
              <Grid size={{ xs: 12, lg: 6 }}>
                <WidgetCard
                  title="At-Risk Projects"
                  subtitle="Open projects that are past their planned end date or have no deliverables logged"
                >
                  {atRiskProjects.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No open projects are currently at risk.
                    </Typography>
                  ) : (
                    <List dense disablePadding>
                      {atRiskProjects.map(({ project, reasons }) => (
                        <ListItem
                          key={project.id}
                          disableGutters
                          divider
                          sx={{ py: 1 }}
                          secondaryAction={
                            <Stack direction="row" spacing={0.5}>
                              {reasons.map((reason) => (
                                <Chip key={reason} size="small" color="error" variant="outlined" label={reason} />
                              ))}
                            </Stack>
                          }
                        >
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: '#c0392b1a', color: '#c0392b' }}>
                              <ErrorOutlineIcon fontSize="small" />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={`${project.code} — ${project.name}`}
                            secondary={`${project.department_name} · due ${project.planned_end} · ${project.manager_name}`}
                          />
                        </ListItem>
                      ))}
                    </List>
                  )}
                </WidgetCard>
              </Grid>

              {/* 4. Budget vs Planned */}
              <Grid size={{ xs: 12, lg: 6 }}>
                <WidgetCard
                  title="Budget vs Planned"
                  subtitle="Estimated consumption based on deliverable progress — actual spend isn't tracked yet, so this is a progress-based estimate, not real cost data"
                >
                  {activeProjectsWithProgress.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No active projects.
                    </Typography>
                  ) : (
                    <Stack spacing={2}>
                      {activeProjectsWithProgress.map(({ project, estimatedPct }) => (
                        <Box key={project.id}>
                          <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.5 }}>
                            <Typography variant="body2" fontWeight={600}>
                              {project.code} — {project.name}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              ~${Math.round((project.planned_budget * estimatedPct) / 100).toLocaleString()} of $
                              {Number(project.planned_budget).toLocaleString()} ({estimatedPct}%)
                            </Typography>
                          </Stack>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(estimatedPct, 100)}
                            color={estimatedPct > 90 ? 'warning' : 'primary'}
                            sx={{ height: 8, borderRadius: 1 }}
                          />
                        </Box>
                      ))}
                    </Stack>
                  )}
                </WidgetCard>
              </Grid>

              {/* 5. Deliverables Progress — stacked bar chart, per project */}
              <Grid size={12}>
                <WidgetCard
                  title="Deliverables Progress"
                  subtitle={`${totalDeliverables} deliverables across ${deliverablesByProjectChartData.length} project${deliverablesByProjectChartData.length === 1 ? '' : 's'}`}
                >
                  {deliverablesByProjectChartData.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No deliverables yet.
                    </Typography>
                  ) : (
                    <Box sx={{ width: '100%', height: 320 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={deliverablesByProjectChartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="project" tick={{ fontSize: 12 }} />
                          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                          <RechartsTooltip />
                          <Legend formatter={(value) => value.replace(/_/g, ' ')} />
                          {Object.keys(DELIVERABLE_STATUS_COLORS).map((status) => (
                            <Bar
                              key={status}
                              dataKey={status}
                              stackId="status"
                              name={status}
                              fill={DELIVERABLE_STATUS_COLORS[status]}
                            />
                          ))}
                        </BarChart>
                      </ResponsiveContainer>
                    </Box>
                  )}
                </WidgetCard>
              </Grid>
            </Grid>

            <Divider />
            <Typography variant="caption" color="text.secondary">
              Data refreshes on page load. Figures are computed from the Projects, Deliverables, and Allocations
              services.
            </Typography>
          </Stack>
        )}
      </Box>
    </AppLayout>
  )
}
