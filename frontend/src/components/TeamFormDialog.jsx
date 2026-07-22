import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from '@mui/material'

import { ApiError } from '../services/api'
import { createTeam, fetchDepartments, fetchUsers, updateTeam } from '../services/teamService'

const EMPTY_FORM = { name: '', description: '', department_id: '', manager_id: '', is_active: true }

function toFormState(team) {
  return team
    ? {
        name: team.name || '',
        description: team.description || '',
        department_id: team.department_id || '',
        manager_id: team.manager_id || '',
        is_active: team.is_active ?? true,
      }
    : EMPTY_FORM
}

// The department/manager dropdowns only offer active departments/users
// (directory-service). If the team being edited was assigned one that's
// since gone inactive, it would otherwise vanish from the Select with no
// explanation — so it's kept as a labelled option instead of being dropped.
function withCurrentValue(options, currentId, currentLabel) {
  if (!currentId || options.some((option) => option.id === currentId)) return options
  return [...options, { id: currentId, label: `${currentLabel} (inactive)` }]
}

/**
 * Create/edit form for a team. Pass `team` to edit it, omit it to create a
 * new one. The caller must remount this on each open (e.g. a `key` derived
 * from the target team) — the form's initial state is only ever read once,
 * from `team`, at mount.
 */
export default function TeamFormDialog({ open, team, onClose, onSaved }) {
  const isEdit = Boolean(team)

  const [form, setForm] = useState(() => toFormState(team))
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
      name: form.name.trim(),
      description: form.description.trim() || null,
      department_id: form.department_id,
      manager_id: form.manager_id,
      is_active: form.is_active,
    }

    try {
      const saved = isEdit ? await updateTeam(team.id, payload) : await createTeam(payload)
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

  const canSubmit = form.name.trim().length >= 2 && form.department_id && form.manager_id

  const departmentOptions = withCurrentValue(
    departments.map((dept) => ({ id: dept.id, label: dept.name })),
    team?.department_id,
    team?.department_name,
  )
  const managerOptions = withCurrentValue(
    users.map((user) => ({ id: user.id, label: `${user.full_name} — ${user.email}` })),
    team?.manager_id,
    team?.manager_name,
  )

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>{isEdit ? `Edit ${team.name}` : 'Create Team'}</DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            {optionsError && <Alert severity="warning">{optionsError}</Alert>}

            <TextField
              label="Name"
              value={form.name}
              onChange={(event) => setField('name', event.target.value)}
              error={Boolean(fieldErrors.name)}
              helperText={fieldErrors.name || ' '}
              required
              fullWidth
              autoFocus
              disabled={submitting}
            />
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
            <TextField
              select
              label="Department"
              value={form.department_id}
              onChange={(event) => setField('department_id', event.target.value)}
              error={Boolean(fieldErrors.department_id)}
              helperText={fieldErrors.department_id || (optionsLoading ? 'Loading departments...' : ' ')}
              required
              fullWidth
              disabled={submitting || optionsLoading}
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
              fullWidth
              disabled={submitting || optionsLoading}
            >
              {managerOptions.map((option) => (
                <MenuItem key={option.id} value={option.id}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={form.is_active}
                  onChange={(event) => setField('is_active', event.target.checked)}
                  disabled={submitting}
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={submitting || !canSubmit}>
            {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Team'}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}
