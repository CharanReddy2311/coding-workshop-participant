import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { DesktopDatePicker } from '@mui/x-date-pickers/DesktopDatePicker'
import { isValid, parseISO } from 'date-fns'
import { format } from 'date-fns/format'

import { ApiError } from '../services/api'
import { fetchDepartments, fetchUsers } from '../services/directoryService'
import { createProject, updateProject } from '../services/projectService'

// Mirrors backend/projects-service/schema.py exactly.
const STATUSES = ['PLANNING', 'ACTIVE', 'ON_HOLD', 'COMPLETED', 'CANCELLED']
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const EMPTY_FORM = {
  code: '',
  name: '',
  description: '',
  department_id: '',
  manager_id: '',
  status: 'PLANNING',
  priority: 'MEDIUM',
  start_date: '',
  planned_end: '',
  actual_end: '',
  planned_budget: '0',
}

function toFormState(project) {
  return project
    ? {
        code: project.code || '',
        name: project.name || '',
        description: project.description || '',
        department_id: project.department_id || '',
        manager_id: project.manager_id || '',
        status: project.status || 'PLANNING',
        priority: project.priority || 'MEDIUM',
        start_date: project.start_date || '',
        planned_end: project.planned_end || '',
        actual_end: project.actual_end || '',
        planned_budget: project.planned_budget != null ? String(project.planned_budget) : '0',
      }
    : EMPTY_FORM
}

// The department/manager dropdowns only offer active departments/users
// (directory-service). If the project being edited was assigned one that's
// since gone inactive, it would otherwise vanish from the Select with no
// explanation — so it's kept as a labelled option instead of being dropped.
function withCurrentValue(options, currentId, currentLabel) {
  if (!currentId || options.some((option) => option.id === currentId)) return options
  return [...options, { id: currentId, label: `${currentLabel} (inactive)` }]
}

// The form stores dates as the plain 'yyyy-MM-dd' strings the backend
// expects; DatePicker works in Date objects, so these convert at the edges.
function toDateValue(value) {
  if (!value) return null
  const parsed = parseISO(value)
  return isValid(parsed) ? parsed : null
}

function toDateString(date) {
  return date && isValid(date) ? format(date, 'yyyy-MM-dd') : ''
}

const fieldSx = { flex: '1 1 220px' }

/**
 * Create/edit form for a project. Pass `project` to edit it, omit it to
 * create a new one. The caller must remount this on each open (e.g. a `key`
 * derived from the target project) — the form's initial state is only ever
 * read once, from `project`, at mount.
 */
export default function ProjectFormDialog({ open, project, onClose, onSaved }) {
  const isEdit = Boolean(project)
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'))

  const [form, setForm] = useState(() => toFormState(project))
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [departments, setDepartments] = useState([])
  const [users, setUsers] = useState([])
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      setOptionsLoading(true)
      setOptionsError('')
      try {
        const [depts, people] = await Promise.all([fetchDepartments(), fetchUsers()])
        if (cancelled) return
        setDepartments(depts)
        setUsers(people)
      } catch (err) {
        if (!cancelled) setOptionsError(err.message || 'Could not load departments/users')
      } finally {
        if (!cancelled) setOptionsLoading(false)
      }
    }

    loadOptions()
    return () => {
      cancelled = true
    }
  }, [])

  function setField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }))
    setFieldErrors((prev) => (prev[name] ? { ...prev, [name]: undefined } : prev))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setFormError('')
    setFieldErrors({})

    const payload = {
      code: form.code.trim(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      department_id: form.department_id,
      manager_id: form.manager_id,
      status: form.status,
      priority: form.priority,
      start_date: form.start_date,
      planned_end: form.planned_end,
      actual_end: form.actual_end || null,
      planned_budget: form.planned_budget === '' ? 0 : Number(form.planned_budget),
    }

    try {
      const saved = isEdit ? await updateProject(project.id, payload) : await createProject(payload)
      onSaved(saved)
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.details || {})
        setFormError(err.message)
      } else {
        setFormError('Something went wrong. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit =
    form.code.trim().length >= 2 &&
    form.name.trim().length >= 3 &&
    form.department_id &&
    form.manager_id &&
    form.start_date &&
    form.planned_end

  const departmentOptions = withCurrentValue(
    departments.map((dept) => ({ id: dept.id, label: dept.name })),
    project?.department_id,
    project?.department_name,
  )
  const managerOptions = withCurrentValue(
    users.map((user) => ({ id: user.id, label: `${user.full_name} — ${user.email}` })),
    project?.manager_id,
    project?.manager_name,
  )

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} fullWidth maxWidth="md" fullScreen={fullScreen}>
      <DialogTitle>{isEdit ? `Edit ${project.name}` : 'Create Project'}</DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            {optionsError && <Alert severity="warning">{optionsError}</Alert>}

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                label="Code"
                value={form.code}
                onChange={(event) => setField('code', event.target.value)}
                error={Boolean(fieldErrors.code)}
                helperText={fieldErrors.code || ' '}
                required
                autoFocus
                disabled={submitting}
                sx={{ flex: '1 1 140px' }}
              />
              <TextField
                label="Name"
                value={form.name}
                onChange={(event) => setField('name', event.target.value)}
                error={Boolean(fieldErrors.name)}
                helperText={fieldErrors.name || ' '}
                required
                disabled={submitting}
                sx={{ flex: '2 1 260px' }}
              />
            </Box>

            <TextField
              label="Description"
              value={form.description}
              onChange={(event) => setField('description', event.target.value)}
              error={Boolean(fieldErrors.description)}
              helperText={fieldErrors.description || ' '}
              fullWidth
              multiline
              minRows={2}
              disabled={submitting}
            />

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                select
                label="Department"
                value={form.department_id}
                onChange={(event) => setField('department_id', event.target.value)}
                error={Boolean(fieldErrors.department_id)}
                helperText={fieldErrors.department_id || (optionsLoading ? 'Loading departments...' : ' ')}
                required
                disabled={submitting || optionsLoading}
                sx={fieldSx}
              >
                {departmentOptions.map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Manager"
                value={form.manager_id}
                onChange={(event) => setField('manager_id', event.target.value)}
                error={Boolean(fieldErrors.manager_id)}
                helperText={fieldErrors.manager_id || (optionsLoading ? 'Loading users...' : ' ')}
                required
                disabled={submitting || optionsLoading}
                sx={fieldSx}
              >
                {managerOptions.map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                select
                label="Status"
                value={form.status}
                onChange={(event) => setField('status', event.target.value)}
                error={Boolean(fieldErrors.status)}
                helperText={fieldErrors.status || ' '}
                disabled={submitting}
                sx={fieldSx}
              >
                {STATUSES.map((status) => (
                  <MenuItem key={status} value={status}>
                    {status.replace('_', ' ')}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Priority"
                value={form.priority}
                onChange={(event) => setField('priority', event.target.value)}
                error={Boolean(fieldErrors.priority)}
                helperText={fieldErrors.priority || ' '}
                disabled={submitting}
                sx={fieldSx}
              >
                {PRIORITIES.map((priority) => (
                  <MenuItem key={priority} value={priority}>
                    {priority}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <DesktopDatePicker
                label="Start Date"
                value={toDateValue(form.start_date)}
                onChange={(date) => setField('start_date', toDateString(date))}
                format="yyyy-MM-dd"
                disabled={submitting}
                slotProps={{
                  textField: {
                    required: true,
                    error: Boolean(fieldErrors.start_date),
                    helperText: fieldErrors.start_date || ' ',
                    sx: fieldSx,
                  },
                }}
              />
              <DesktopDatePicker
                label="Planned End"
                value={toDateValue(form.planned_end)}
                onChange={(date) => setField('planned_end', toDateString(date))}
                format="yyyy-MM-dd"
                disabled={submitting}
                slotProps={{
                  textField: {
                    required: true,
                    error: Boolean(fieldErrors.planned_end),
                    helperText: fieldErrors.planned_end || ' ',
                    sx: fieldSx,
                  },
                }}
              />
            </Box>

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <DesktopDatePicker
                label="Actual End"
                value={toDateValue(form.actual_end)}
                onChange={(date) => setField('actual_end', toDateString(date))}
                format="yyyy-MM-dd"
                disabled={submitting}
                slotProps={{
                  textField: {
                    error: Boolean(fieldErrors.actual_end),
                    helperText: fieldErrors.actual_end || 'Required once the project is Completed',
                    sx: fieldSx,
                  },
                  field: { clearable: true },
                }}
              />
              <TextField
                type="number"
                label="Planned Budget"
                value={form.planned_budget}
                onChange={(event) => setField('planned_budget', event.target.value)}
                error={Boolean(fieldErrors.planned_budget)}
                helperText={fieldErrors.planned_budget || ' '}
                slotProps={{ htmlInput: { min: 0, step: '0.01' } }}
                disabled={submitting}
                sx={fieldSx}
              />
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={submitting || !canSubmit}>
            {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Project'}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}
