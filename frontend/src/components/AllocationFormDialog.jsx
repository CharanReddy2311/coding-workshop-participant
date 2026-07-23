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
import { createAllocation, updateAllocation } from '../services/allocationService'
import { fetchUsers } from '../services/directoryService'
import { listProjects } from '../services/projectService'

const EMPTY_FORM = {
  user_id: '',
  project_id: '',
  role_on_project: '',
  allocation_pct: '50',
  start_date: '',
  end_date: '',
}

function toFormState(allocation) {
  return allocation
    ? {
        user_id: allocation.user_id || '',
        project_id: allocation.project_id || '',
        role_on_project: allocation.role_on_project || '',
        allocation_pct: String(allocation.allocation_pct ?? 50),
        start_date: allocation.start_date || '',
        end_date: allocation.end_date || '',
      }
    : EMPTY_FORM
}

// The user/project dropdowns only offer what's currently listable. If the
// allocation being edited references something no longer in that list (an
// inactive user, say), keep it as a labelled option instead of quietly
// blanking the field.
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

const fieldSx = { flex: '1 1 200px' }

/**
 * Create/edit form for an allocation. Pass `allocation` to edit it, omit it
 * to create a new one. The caller must remount this on each open (e.g. a
 * `key` derived from the target allocation) — the form's initial state is
 * only ever read once, from `allocation`, at mount.
 */
export default function AllocationFormDialog({ open, allocation, onClose, onSaved }) {
  const isEdit = Boolean(allocation)
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'))

  const [form, setForm] = useState(() => toFormState(allocation))
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [users, setUsers] = useState([])
  const [projects, setProjects] = useState([])
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      setOptionsLoading(true)
      setOptionsError('')
      try {
        const [people, { projects: projectRows }] = await Promise.all([
          fetchUsers(),
          listProjects({ limit: 200, sort: 'name', order: 'asc' }),
        ])
        if (cancelled) return
        setUsers(people)
        setProjects(projectRows)
      } catch (err) {
        if (!cancelled) setOptionsError(err.message || 'Could not load users/projects')
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
      user_id: form.user_id,
      project_id: form.project_id,
      role_on_project: form.role_on_project.trim() || null,
      allocation_pct: form.allocation_pct === '' ? 0 : Number(form.allocation_pct),
      start_date: form.start_date,
      end_date: form.end_date,
    }

    try {
      const saved = isEdit ? await updateAllocation(allocation.id, payload) : await createAllocation(payload)
      onSaved(saved)
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.details || {})
        // The over-allocation conflict has no single field to attach to —
        // spell the numbers out in the banner instead of just the message.
        if (err.code === 'conflict' && err.details?.projected_pct != null) {
          const { existing_pct: existingPct, requested_pct: requestedPct, projected_pct: projectedPct, max_pct: maxPct } =
            err.details
          setFormError(
            `${err.message} (existing ${existingPct}% + requested ${requestedPct}% = ${projectedPct}%, max ${maxPct}%)`,
          )
        } else {
          setFormError(err.message)
        }
      } else {
        setFormError('Something went wrong. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit = form.user_id && form.project_id && form.allocation_pct && form.start_date && form.end_date

  const userOptions = withCurrentValue(
    users.map((user) => ({ id: user.id, label: `${user.full_name} — ${user.email}` })),
    allocation?.user_id,
    allocation?.user_name,
  )
  const projectOptions = withCurrentValue(
    projects.map((project) => ({ id: project.id, label: `${project.code} — ${project.name}` })),
    allocation?.project_id,
    allocation?.project_code ? `${allocation.project_code} — ${allocation.project_name}` : allocation?.project_name,
  )

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>{isEdit ? 'Edit Allocation' : 'Create Allocation'}</DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            {optionsError && <Alert severity="warning">{optionsError}</Alert>}

            <TextField
              select
              label="User"
              value={form.user_id}
              onChange={(event) => setField('user_id', event.target.value)}
              error={Boolean(fieldErrors.user_id)}
              helperText={fieldErrors.user_id || (optionsLoading ? 'Loading users...' : ' ')}
              required
              fullWidth
              autoFocus
              disabled={submitting || optionsLoading}
            >
              {userOptions.map((option) => (
                <MenuItem key={option.id} value={option.id}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              select
              label="Project"
              value={form.project_id}
              onChange={(event) => setField('project_id', event.target.value)}
              error={Boolean(fieldErrors.project_id)}
              helperText={fieldErrors.project_id || (optionsLoading ? 'Loading projects...' : ' ')}
              required
              fullWidth
              disabled={submitting || optionsLoading}
            >
              {projectOptions.map((option) => (
                <MenuItem key={option.id} value={option.id}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              label="Role on Project"
              value={form.role_on_project}
              onChange={(event) => setField('role_on_project', event.target.value)}
              error={Boolean(fieldErrors.role_on_project)}
              helperText={fieldErrors.role_on_project || ' '}
              fullWidth
              disabled={submitting}
            />

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
                label="End Date"
                value={toDateValue(form.end_date)}
                onChange={(date) => setField('end_date', toDateString(date))}
                format="yyyy-MM-dd"
                disabled={submitting}
                slotProps={{
                  textField: {
                    required: true,
                    error: Boolean(fieldErrors.end_date),
                    helperText: fieldErrors.end_date || ' ',
                    sx: fieldSx,
                  },
                }}
              />
              <TextField
                type="number"
                label="Allocation %"
                value={form.allocation_pct}
                onChange={(event) => setField('allocation_pct', event.target.value)}
                error={Boolean(fieldErrors.allocation_pct)}
                helperText={fieldErrors.allocation_pct || ' '}
                required
                slotProps={{ htmlInput: { min: 1, max: 100 } }}
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
            {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Allocation'}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}
