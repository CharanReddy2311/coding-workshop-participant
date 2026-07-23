import { useEffect, useState } from 'react'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'

import AppLayout from '../components/AppLayout'
import DeliverableFormDialog from '../components/DeliverableFormDialog'
import { useAuth } from '../context/AuthContext'
import { deleteDeliverable, listDeliverables } from '../services/deliverableService'
import { listProjects } from '../services/projectService'

// Mirrors backend/deliverables-service/schema.py exactly.
const STATUSES = ['NOT_STARTED', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED']
const OPEN_STATUSES = ['NOT_STARTED', 'IN_PROGRESS', 'BLOCKED']

const STATUS_COLORS = {
  NOT_STARTED: 'default',
  IN_PROGRESS: 'info',
  BLOCKED: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'error',
}

const today = new Date().toISOString().slice(0, 10)

function isOverdue(deliverable) {
  return OPEN_STATUSES.includes(deliverable.status) && deliverable.due_date < today
}

// Drop the columns you need least to identify a row and act on it, so the
// table stays usable without horizontal scrolling on a phone.
const hideOnMobile = { display: { xs: 'none', sm: 'table-cell' } }

export default function Deliverables() {
  const { hasRole } = useAuth()

  // Matches backend/deliverables-service/function.py PERMISSIONS: Contributor+
  // for both create and edit, Admin only for delete.
  const canCreate = hasRole('CONTRIBUTOR')
  const canEdit = hasRole('CONTRIBUTOR')
  const canDelete = hasRole('MANAGER')

  const [deliverables, setDeliverables] = useState([])
  const [meta, setMeta] = useState({ total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [projectOptions, setProjectOptions] = useState([])

  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [refreshKey, setRefreshKey] = useState(0)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKey, setDialogKey] = useState(0)
  const [editingDeliverable, setEditingDeliverable] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [snackbar, setSnackbar] = useState('')

  // Debounce free-text search so every keystroke doesn't fire a request.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(0)
    }, 400)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    let cancelled = false
    listProjects({ limit: 200, sort: 'name', order: 'asc' })
      .then(({ projects }) => {
        if (!cancelled) setProjectOptions(projects)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function fetchDeliverables() {
      setLoading(true)
      setError('')

      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
        sort: 'due_date',
        order: 'asc',
      }
      if (debouncedSearch) params.q = debouncedSearch
      if (statusFilter) params.status = statusFilter
      if (projectFilter) params.project_id = projectFilter

      try {
        const { deliverables: rows, meta: pageMeta } = await listDeliverables(params)
        if (cancelled) return
        setDeliverables(rows)
        setMeta(pageMeta)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load deliverables')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchDeliverables()
    return () => {
      cancelled = true
    }
  }, [debouncedSearch, statusFilter, projectFilter, page, rowsPerPage, refreshKey])

  function openCreate() {
    setEditingDeliverable(null)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function openEdit(deliverable) {
    setEditingDeliverable(deliverable)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function handleSaved(saved) {
    setDialogOpen(false)
    setSnackbar(`Deliverable "${saved.name}" ${editingDeliverable ? 'updated' : 'created'}`)
    setRefreshKey((key) => key + 1)
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteDeliverable(deleteTarget.id)
      setSnackbar(`Deliverable "${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      // Deleting the last row on a page would otherwise strand the view
      // past the new last page.
      if (deliverables.length === 1 && page > 0) {
        setPage((p) => p - 1)
      } else {
        setRefreshKey((key) => key + 1)
      }
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete deliverable')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppLayout>
      <Box sx={{ maxWidth: 1300, mx: 'auto', p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            Deliverables
          </Typography>
          <Tooltip title={canCreate ? '' : 'Requires the Contributor role or higher'}>
            <span>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={openCreate}
                disabled={!canCreate}
              >
                Create Deliverable
              </Button>
            </span>
          </Tooltip>
        </Box>

        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <TextField
            label="Search by name"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            size="small"
            sx={{ minWidth: 240 }}
          />
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="status-filter-label">Status</InputLabel>
            <Select
              labelId="status-filter-label"
              label="Status"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value)
                setPage(0)
              }}
            >
              <MenuItem value="">All Statuses</MenuItem>
              {STATUSES.map((status) => (
                <MenuItem key={status} value={status}>
                  {status.replace(/_/g, ' ')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="project-filter-label">Project</InputLabel>
            <Select
              labelId="project-filter-label"
              label="Project"
              value={projectFilter}
              onChange={(event) => {
                setProjectFilter(event.target.value)
                setPage(0)
              }}
            >
              <MenuItem value="">All Projects</MenuItem>
              {projectOptions.map((project) => (
                <MenuItem key={project.id} value={project.id}>
                  {project.code} — {project.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Paper>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Deliverable</TableCell>
                  <TableCell sx={hideOnMobile}>Project</TableCell>
                  <TableCell sx={hideOnMobile}>Owner</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Progress</TableCell>
                  <TableCell>Due Date</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 5 }}>
                      <CircularProgress size={28} />
                    </TableCell>
                  </TableRow>
                )}

                {!loading && deliverables.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 5 }}>
                      <Typography color="text.secondary">No deliverables found.</Typography>
                    </TableCell>
                  </TableRow>
                )}

                {!loading &&
                  deliverables.map((deliverable) => (
                    <TableRow key={deliverable.id} hover>
                      <TableCell>
                        <Typography fontWeight={600}>{deliverable.name}</Typography>
                        {deliverable.description && (
                          <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: 260 }}>
                            {deliverable.description}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell sx={hideOnMobile}>
                        {deliverable.project_code} — {deliverable.project_name}
                      </TableCell>
                      <TableCell sx={hideOnMobile}>{deliverable.owner_name || '—'}</TableCell>
                      <TableCell>
                        <Chip
                          label={deliverable.status.replace(/_/g, ' ')}
                          color={STATUS_COLORS[deliverable.status]}
                          size="small"
                        />
                      </TableCell>
                      <TableCell sx={{ minWidth: 130 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <LinearProgress
                            variant="determinate"
                            value={deliverable.percent_complete}
                            sx={{ flexGrow: 1, height: 6, borderRadius: 1 }}
                          />
                          <Typography variant="body2" color="text.secondary">
                            {deliverable.percent_complete}%
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          color={isOverdue(deliverable) ? 'error' : 'text.primary'}
                          fontWeight={isOverdue(deliverable) ? 600 : 400}
                        >
                          {deliverable.due_date}
                          {isOverdue(deliverable) ? ' (overdue)' : ''}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title={canEdit ? 'Edit' : 'Requires the Contributor role or higher'}>
                          <span>
                            <IconButton size="small" onClick={() => openEdit(deliverable)} disabled={!canEdit}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title={canDelete ? 'Delete' : 'Requires the Manager role'}>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteTarget(deliverable)}
                              disabled={!canDelete}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableContainer>

          <TablePagination
            component="div"
            count={meta.total || 0}
            page={page}
            onPageChange={(_event, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(event) => {
              setRowsPerPage(parseInt(event.target.value, 10))
              setPage(0)
            }}
            rowsPerPageOptions={[10, 25, 50]}
          />
        </Paper>
      </Box>

      <DeliverableFormDialog
        key={dialogKey}
        open={dialogOpen}
        deliverable={editingDeliverable}
        onClose={() => setDialogOpen(false)}
        onSaved={handleSaved}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={deleting ? undefined : () => setDeleteTarget(null)}>
        <DialogTitle>Delete deliverable?</DialogTitle>
        <DialogContent>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <DialogContentText>
            This permanently deletes <strong>{deleteTarget?.name}</strong> and any dependency links to it. This
            cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>
            Cancel
          </Button>
          <Button onClick={confirmDelete} color="error" variant="contained" disabled={deleting}>
            {deleting ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={Boolean(snackbar)}
        autoHideDuration={4000}
        onClose={() => setSnackbar('')}
        message={snackbar}
      />
    </AppLayout>
  )
}
