import { useEffect, useState } from 'react'
import DeleteIcon from '@mui/icons-material/Delete'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'

import { ApiError } from '../services/api'
import {
  addDependency,
  createDeliverable,
  listDependencies,
  listDeliverables,
  removeDependency,
  updateDeliverable,
} from '../services/deliverableService'
import { fetchUsers } from '../services/directoryService'
import { listProjects } from '../services/projectService'

// Mirrors backend/deliverables-service/schema.py exactly.
const STATUSES = ['NOT_STARTED', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED']
const DEP_TYPES = ['FINISH_TO_START', 'START_TO_START', 'FINISH_TO_FINISH']

const EMPTY_FORM = {
  project_id: '',
  owner_id: '',
  name: '',
  description: '',
  status: 'NOT_STARTED',
  percent_complete: '0',
  weight: '1',
  due_date: '',
  completed_at: '',
}

function toFormState(deliverable) {
  return deliverable
    ? {
        project_id: deliverable.project_id || '',
        owner_id: deliverable.owner_id || '',
        name: deliverable.name || '',
        description: deliverable.description || '',
        status: deliverable.status || 'NOT_STARTED',
        percent_complete: String(deliverable.percent_complete ?? 0),
        weight: deliverable.weight != null ? String(deliverable.weight) : '1',
        due_date: deliverable.due_date || '',
        completed_at: deliverable.completed_at || '',
      }
    : EMPTY_FORM
}

// The project/owner dropdowns only offer what's currently listable. If the
// deliverable being edited references something no longer in that list
// (an inactive user, say), keep it as a labelled option instead of quietly
// blanking the field.
function withCurrentValue(options, currentId, currentLabel) {
  if (!currentId || options.some((option) => option.id === currentId)) return options
  return [...options, { id: currentId, label: `${currentLabel} (inactive)` }]
}

const rowSx = { display: 'flex', gap: 2, flexWrap: 'wrap' }

/**
 * Create/edit form for a deliverable. Pass `deliverable` to edit it, omit it
 * to create a new one. The caller must remount this on each open (e.g. a
 * `key` derived from the target deliverable) — the form's initial state is
 * only ever read once, from `deliverable`, at mount.
 */
export default function DeliverableFormDialog({ open, deliverable, onClose, onSaved }) {
  const isEdit = Boolean(deliverable)

  const [form, setForm] = useState(() => toFormState(deliverable))
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [projects, setProjects] = useState([])
  const [users, setUsers] = useState([])
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      setOptionsLoading(true)
      setOptionsError('')
      try {
        const [{ projects: projectRows }, people] = await Promise.all([
          listProjects({ limit: 200, sort: 'name', order: 'asc' }),
          fetchUsers(),
        ])
        if (cancelled) return
        setProjects(projectRows)
        setUsers(people)
      } catch (err) {
        if (!cancelled) setOptionsError(err.message || 'Could not load projects/users')
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
      project_id: form.project_id,
      owner_id: form.owner_id || null,
      name: form.name.trim(),
      description: form.description.trim() || null,
      status: form.status,
      percent_complete: form.percent_complete === '' ? 0 : Number(form.percent_complete),
      weight: form.weight === '' ? 1 : Number(form.weight),
      due_date: form.due_date,
      completed_at: form.completed_at || null,
    }

    try {
      const saved = isEdit
        ? await updateDeliverable(deliverable.id, payload)
        : await createDeliverable(payload)
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

  const canSubmit = form.project_id && form.name.trim().length >= 2 && form.due_date

  const projectOptions = withCurrentValue(
    projects.map((p) => ({ id: p.id, label: `${p.code} — ${p.name}` })),
    deliverable?.project_id,
    deliverable?.project_code ? `${deliverable.project_code} — ${deliverable.project_name}` : deliverable?.project_name,
  )
  const ownerOptions = withCurrentValue(
    users.map((u) => ({ id: u.id, label: `${u.full_name} — ${u.email}` })),
    deliverable?.owner_id,
    deliverable?.owner_name,
  )

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle>{isEdit ? `Edit ${deliverable.name}` : 'Create Deliverable'}</DialogTitle>
      <Box component="form" onSubmit={handleSubmit}>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            {optionsError && <Alert severity="warning">{optionsError}</Alert>}

            <Box sx={rowSx}>
              <TextField
                select
                label="Project"
                value={form.project_id}
                onChange={(event) => setField('project_id', event.target.value)}
                error={Boolean(fieldErrors.project_id)}
                helperText={fieldErrors.project_id || (optionsLoading ? 'Loading projects...' : ' ')}
                required
                autoFocus
                disabled={submitting || optionsLoading}
                sx={{ flex: '1 1 240px' }}
              >
                {projectOptions.map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Owner (optional)"
                value={form.owner_id}
                onChange={(event) => setField('owner_id', event.target.value)}
                error={Boolean(fieldErrors.owner_id)}
                helperText={fieldErrors.owner_id || (optionsLoading ? 'Loading users...' : ' ')}
                disabled={submitting || optionsLoading}
                sx={{ flex: '1 1 240px' }}
              >
                <MenuItem value="">— Unassigned —</MenuItem>
                {ownerOptions.map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <TextField
              label="Name"
              value={form.name}
              onChange={(event) => setField('name', event.target.value)}
              error={Boolean(fieldErrors.name)}
              helperText={fieldErrors.name || ' '}
              required
              fullWidth
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

            <Box sx={rowSx}>
              <TextField
                select
                label="Status"
                value={form.status}
                onChange={(event) => setField('status', event.target.value)}
                error={Boolean(fieldErrors.status)}
                helperText={fieldErrors.status || ' '}
                disabled={submitting}
                sx={{ flex: '1 1 160px' }}
              >
                {STATUSES.map((status) => (
                  <MenuItem key={status} value={status}>
                    {status.replace(/_/g, ' ')}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                type="number"
                label="% Complete"
                value={form.percent_complete}
                onChange={(event) => setField('percent_complete', event.target.value)}
                error={Boolean(fieldErrors.percent_complete)}
                helperText={fieldErrors.percent_complete || ' '}
                slotProps={{ htmlInput: { min: 0, max: 100 } }}
                disabled={submitting}
                sx={{ flex: '1 1 140px' }}
              />
              <TextField
                type="number"
                label="Weight"
                value={form.weight}
                onChange={(event) => setField('weight', event.target.value)}
                error={Boolean(fieldErrors.weight)}
                helperText={fieldErrors.weight || ' '}
                slotProps={{ htmlInput: { min: 0.01, step: '0.01' } }}
                disabled={submitting}
                sx={{ flex: '1 1 140px' }}
              />
            </Box>

            <Box sx={rowSx}>
              <TextField
                type="date"
                label="Due Date"
                value={form.due_date}
                onChange={(event) => setField('due_date', event.target.value)}
                error={Boolean(fieldErrors.due_date)}
                helperText={fieldErrors.due_date || ' '}
                required
                disabled={submitting}
                slotProps={{ inputLabel: { shrink: true } }}
                sx={{ flex: '1 1 200px' }}
              />
              <TextField
                type="date"
                label="Completed On"
                value={form.completed_at}
                onChange={(event) => setField('completed_at', event.target.value)}
                error={Boolean(fieldErrors.completed_at)}
                helperText={fieldErrors.completed_at || 'Required once marked Completed'}
                disabled={submitting}
                slotProps={{ inputLabel: { shrink: true } }}
                sx={{ flex: '1 1 200px' }}
              />
            </Box>

            {isEdit && (
              <>
                <Divider />
                <DependenciesSection deliverable={deliverable} disabled={submitting} />
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={submitting || !canSubmit}>
            {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Deliverable'}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  )
}

/** Compact predecessor/successor edge manager for one deliverable. */
function DependenciesSection({ deliverable, disabled }) {
  const [predecessors, setPredecessors] = useState([])
  const [successors, setSuccessors] = useState([])
  const [siblings, setSiblings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newPredecessorId, setNewPredecessorId] = useState('')
  const [newDepType, setNewDepType] = useState('FINISH_TO_START')
  const [busy, setBusy] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const [deps, { deliverables: rows }] = await Promise.all([
          listDependencies(deliverable.id),
          listDeliverables({ project_id: deliverable.project_id, limit: 200 }),
        ])
        if (cancelled) return
        setPredecessors(deps.predecessors)
        setSuccessors(deps.successors)
        setSiblings(rows.filter((row) => row.id !== deliverable.id))
      } catch (err) {
        if (!cancelled) setError(err.message || 'Could not load dependencies')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [deliverable.id, deliverable.project_id, refreshKey])

  async function handleAdd() {
    if (!newPredecessorId) return
    setBusy(true)
    setError('')
    try {
      await addDependency(deliverable.id, { predecessor_id: newPredecessorId, dep_type: newDepType })
      setNewPredecessorId('')
      setRefreshKey((key) => key + 1)
    } catch (err) {
      setError(err.message || 'Could not add dependency')
    } finally {
      setBusy(false)
    }
  }

  async function handleRemovePredecessor(predecessorId) {
    setBusy(true)
    setError('')
    try {
      await removeDependency(deliverable.id, predecessorId)
      setRefreshKey((key) => key + 1)
    } catch (err) {
      setError(err.message || 'Could not remove dependency')
    } finally {
      setBusy(false)
    }
  }

  // Removing a "blocks" edge is a delete on the *other* deliverable's
  // dependency list — this deliverable is that edge's predecessor.
  async function handleRemoveSuccessor(successorId) {
    setBusy(true)
    setError('')
    try {
      await removeDependency(successorId, deliverable.id)
      setRefreshKey((key) => key + 1)
    } catch (err) {
      setError(err.message || 'Could not remove dependency')
    } finally {
      setBusy(false)
    }
  }

  const availableCandidates = siblings.filter(
    (sibling) => !predecessors.some((predecessor) => predecessor.id === sibling.id),
  )

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Dependencies
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Loading...
        </Typography>
      ) : (
        <Stack spacing={1.5}>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Blocked by
            </Typography>
            {predecessors.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Nothing blocking this deliverable.
              </Typography>
            ) : (
              <List dense disablePadding>
                {predecessors.map((predecessor) => (
                  <ListItem
                    key={predecessor.id}
                    disableGutters
                    secondaryAction={
                      <IconButton
                        size="small"
                        onClick={() => handleRemovePredecessor(predecessor.id)}
                        disabled={disabled || busy}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    }
                  >
                    <ListItemText
                      primary={predecessor.name}
                      secondary={`${predecessor.status.replace(/_/g, ' ')} · due ${predecessor.due_date} · ${predecessor.dep_type.replace(/_/g, ' ')}`}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Box>

          <Box>
            <Typography variant="caption" color="text.secondary">
              Blocks
            </Typography>
            {successors.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Nothing depends on this deliverable.
              </Typography>
            ) : (
              <List dense disablePadding>
                {successors.map((successor) => (
                  <ListItem
                    key={successor.id}
                    disableGutters
                    secondaryAction={
                      <IconButton
                        size="small"
                        onClick={() => handleRemoveSuccessor(successor.id)}
                        disabled={disabled || busy}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    }
                  >
                    <ListItemText
                      primary={successor.name}
                      secondary={`${successor.status.replace(/_/g, ' ')} · due ${successor.due_date} · ${successor.dep_type.replace(/_/g, ' ')}`}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Box>

          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <TextField
              select
              size="small"
              label="Add predecessor"
              value={newPredecessorId}
              onChange={(event) => setNewPredecessorId(event.target.value)}
              disabled={disabled || busy || availableCandidates.length === 0}
              sx={{ minWidth: 220 }}
            >
              {availableCandidates.map((candidate) => (
                <MenuItem key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Type"
              value={newDepType}
              onChange={(event) => setNewDepType(event.target.value)}
              disabled={disabled || busy}
              sx={{ minWidth: 180 }}
            >
              {DEP_TYPES.map((type) => (
                <MenuItem key={type} value={type}>
                  {type.replace(/_/g, ' ')}
                </MenuItem>
              ))}
            </TextField>
            <Button
              size="small"
              variant="outlined"
              onClick={handleAdd}
              disabled={disabled || busy || !newPredecessorId}
            >
              Add
            </Button>
          </Box>
        </Stack>
      )}
    </Box>
  )
}
