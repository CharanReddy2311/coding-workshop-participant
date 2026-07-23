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
  Tooltip,
  Typography,
} from '@mui/material'

import AllocationFormDialog from '../components/AllocationFormDialog'
import AppLayout from '../components/AppLayout'
import { useAuth } from '../context/AuthContext'
import { deleteAllocation, listAllocations } from '../services/allocationService'
import { fetchUsers } from '../services/directoryService'
import { listProjects } from '../services/projectService'

const today = new Date().toISOString().slice(0, 10)

function isActive(allocation) {
  return allocation.start_date <= today && today <= allocation.end_date
}

export default function Allocations() {
  const { hasRole } = useAuth()

  // Matches backend/allocations-service/function.py PERMISSIONS: Contributor+
  // for both create and edit, Admin only for delete.
  const canCreate = hasRole('CONTRIBUTOR')
  const canEdit = hasRole('CONTRIBUTOR')
  const canDelete = hasRole('ADMIN')

  const [allocations, setAllocations] = useState([])
  const [meta, setMeta] = useState({ total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [userFilter, setUserFilter] = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [userOptions, setUserOptions] = useState([])
  const [projectOptions, setProjectOptions] = useState([])

  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [refreshKey, setRefreshKey] = useState(0)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKey, setDialogKey] = useState(0)
  const [editingAllocation, setEditingAllocation] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [snackbar, setSnackbar] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadFilterOptions() {
      try {
        const [people, { projects }] = await Promise.all([
          fetchUsers(),
          listProjects({ limit: 200, sort: 'name', order: 'asc' }),
        ])
        if (cancelled) return
        setUserOptions(people)
        setProjectOptions(projects)
      } catch {
        // Filters degrade to "no options" silently; the table itself still loads.
      }
    }

    loadFilterOptions()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function fetchAllocations() {
      setLoading(true)
      setError('')

      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
        sort: 'start_date',
        order: 'desc',
      }
      if (userFilter) params.user_id = userFilter
      if (projectFilter) params.project_id = projectFilter

      try {
        const { allocations: rows, meta: pageMeta } = await listAllocations(params)
        if (cancelled) return
        setAllocations(rows)
        setMeta(pageMeta)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load allocations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchAllocations()
    return () => {
      cancelled = true
    }
  }, [userFilter, projectFilter, page, rowsPerPage, refreshKey])

  function openCreate() {
    setEditingAllocation(null)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function openEdit(allocation) {
    setEditingAllocation(allocation)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function handleSaved() {
    setDialogOpen(false)
    setSnackbar(`Allocation ${editingAllocation ? 'updated' : 'created'}`)
    setRefreshKey((key) => key + 1)
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteAllocation(deleteTarget.id)
      setSnackbar('Allocation deleted')
      setDeleteTarget(null)
      // Deleting the last row on a page would otherwise strand the view
      // past the new last page.
      if (allocations.length === 1 && page > 0) {
        setPage((p) => p - 1)
      } else {
        setRefreshKey((key) => key + 1)
      }
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete allocation')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppLayout>
      <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            Allocations
          </Typography>
          <Tooltip title={canCreate ? '' : 'Requires the Contributor role or higher'}>
            <span>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={openCreate}
                disabled={!canCreate}
              >
                Create Allocation
              </Button>
            </span>
          </Tooltip>
        </Box>

        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 240 }}>
            <InputLabel id="user-filter-label">User</InputLabel>
            <Select
              labelId="user-filter-label"
              label="User"
              value={userFilter}
              onChange={(event) => {
                setUserFilter(event.target.value)
                setPage(0)
              }}
            >
              <MenuItem value="">All Users</MenuItem>
              {userOptions.map((user) => (
                <MenuItem key={user.id} value={user.id}>
                  {user.full_name}
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
                  <TableCell>User</TableCell>
                  <TableCell>Project</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Allocation</TableCell>
                  <TableCell>Period</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 5 }}>
                      <CircularProgress size={28} />
                    </TableCell>
                  </TableRow>
                )}

                {!loading && allocations.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 5 }}>
                      <Typography color="text.secondary">No allocations found.</Typography>
                    </TableCell>
                  </TableRow>
                )}

                {!loading &&
                  allocations.map((allocation) => (
                    <TableRow key={allocation.id} hover>
                      <TableCell>
                        <Typography fontWeight={600}>{allocation.user_name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {allocation.user_email}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {allocation.project_code} — {allocation.project_name}
                      </TableCell>
                      <TableCell>{allocation.role_on_project || '—'}</TableCell>
                      <TableCell>
                        <Chip
                          label={`${allocation.allocation_pct}%`}
                          color={isActive(allocation) ? 'primary' : 'default'}
                          size="small"
                          variant={isActive(allocation) ? 'filled' : 'outlined'}
                        />
                      </TableCell>
                      <TableCell>
                        {allocation.start_date} → {allocation.end_date}
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title={canEdit ? 'Edit' : 'Requires the Contributor role or higher'}>
                          <span>
                            <IconButton size="small" onClick={() => openEdit(allocation)} disabled={!canEdit}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title={canDelete ? 'Delete' : 'Requires the Admin role'}>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteTarget(allocation)}
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

      <AllocationFormDialog
        key={dialogKey}
        open={dialogOpen}
        allocation={editingAllocation}
        onClose={() => setDialogOpen(false)}
        onSaved={handleSaved}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={deleting ? undefined : () => setDeleteTarget(null)}>
        <DialogTitle>Delete allocation?</DialogTitle>
        <DialogContent>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <DialogContentText>
            This permanently removes <strong>{deleteTarget?.user_name}</strong>&apos;s allocation to{' '}
            <strong>{deleteTarget?.project_name}</strong>. This cannot be undone.
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
