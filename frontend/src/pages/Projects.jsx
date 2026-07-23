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
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'

import AppLayout from '../components/AppLayout'
import ProjectFormDialog from '../components/ProjectFormDialog'
import { useAuth } from '../context/AuthContext'
import { fetchDepartments } from '../services/directoryService'
import { deleteProject, listProjects } from '../services/projectService'

// Mirrors backend/projects-service/schema.py exactly.
const STATUSES = ['PLANNING', 'ACTIVE', 'ON_HOLD', 'COMPLETED', 'CANCELLED']
const OPEN_STATUSES = ['PLANNING', 'ACTIVE', 'ON_HOLD']

const STATUS_COLORS = {
  PLANNING: 'default',
  ACTIVE: 'info',
  ON_HOLD: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'error',
}

const PRIORITY_COLORS = {
  LOW: 'default',
  MEDIUM: 'info',
  HIGH: 'warning',
  CRITICAL: 'error',
}

const today = new Date().toISOString().slice(0, 10)

function isOverdue(project) {
  return OPEN_STATUSES.includes(project.status) && project.planned_end < today
}

// This table has 8 columns — too many for a phone. Drop the least critical
// ones first on the smallest screens, and Planned End once we run out of
// room on tablets too. Project name, Status, and Actions always stay.
const hideOnMobile = { display: { xs: 'none', sm: 'table-cell' } }
const hideOnTablet = { display: { xs: 'none', md: 'table-cell' } }

export default function Projects() {
  const { hasRole } = useAuth()

  const canCreate = hasRole('MANAGER')
  const canEdit = hasRole('CONTRIBUTOR')
  const canDelete = hasRole('MANAGER')

  const [projects, setProjects] = useState([])
  const [meta, setMeta] = useState({ total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [departmentOptions, setDepartmentOptions] = useState([])

  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [refreshKey, setRefreshKey] = useState(0)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKey, setDialogKey] = useState(0)
  const [editingProject, setEditingProject] = useState(null)
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

  // Unlike Teams' department filter, this comes straight from
  // directory-service — a complete, reliable list, not a best-effort
  // derivation from whatever's currently on the page.
  useEffect(() => {
    let cancelled = false
    fetchDepartments()
      .then((depts) => {
        if (!cancelled) setDepartmentOptions(depts)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function fetchProjects() {
      setLoading(true)
      setError('')

      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
        sort: 'name',
        order: 'asc',
      }
      if (debouncedSearch) params.q = debouncedSearch
      if (statusFilter) params.status = statusFilter
      if (departmentFilter) params.department_id = departmentFilter

      try {
        const { projects: rows, meta: pageMeta } = await listProjects(params)
        if (cancelled) return
        setProjects(rows)
        setMeta(pageMeta)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load projects')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchProjects()
    return () => {
      cancelled = true
    }
  }, [debouncedSearch, statusFilter, departmentFilter, page, rowsPerPage, refreshKey])

  function openCreate() {
    setEditingProject(null)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function openEdit(project) {
    setEditingProject(project)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function handleSaved(saved) {
    setDialogOpen(false)
    setSnackbar(`Project "${saved.name}" ${editingProject ? 'updated' : 'created'}`)
    setRefreshKey((key) => key + 1)
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteProject(deleteTarget.id)
      setSnackbar(`Project "${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      // Deleting the last row on a page would otherwise strand the view
      // past the new last page.
      if (projects.length === 1 && page > 0) {
        setPage((p) => p - 1)
      } else {
        setRefreshKey((key) => key + 1)
      }
    } catch (err) {
      // projects-service refuses to delete a project with linked
      // deliverables/allocations and includes a hint on how to proceed —
      // surface it verbatim rather than just the generic message.
      const hint = err.details?.hint
      setDeleteError(hint ? `${err.message} ${hint}` : err.message || 'Failed to delete project')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppLayout>
      <Box sx={{ maxWidth: 1300, mx: 'auto', p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            Projects
          </Typography>
          <Tooltip title={canCreate ? '' : 'Requires the Manager or Admin role'}>
            <span>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={openCreate}
                disabled={!canCreate}
              >
                Create Project
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
                  {status.replace('_', ' ')}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="department-filter-label">Department</InputLabel>
            <Select
              labelId="department-filter-label"
              label="Department"
              value={departmentFilter}
              onChange={(event) => {
                setDepartmentFilter(event.target.value)
                setPage(0)
              }}
            >
              <MenuItem value="">All Departments</MenuItem>
              {departmentOptions.map((dept) => (
                <MenuItem key={dept.id} value={dept.id}>
                  {dept.name}
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
                  <TableCell>Project</TableCell>
                  <TableCell sx={hideOnMobile}>Department</TableCell>
                  <TableCell sx={hideOnMobile}>Manager</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell sx={hideOnMobile}>Priority</TableCell>
                  <TableCell sx={hideOnTablet}>Planned End</TableCell>
                  <TableCell align="right" sx={hideOnMobile}>
                    Budget
                  </TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={8} align="center" sx={{ py: 5 }}>
                      <CircularProgress size={28} />
                    </TableCell>
                  </TableRow>
                )}

                {!loading && projects.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} align="center" sx={{ py: 5 }}>
                      <Typography color="text.secondary">No projects found.</Typography>
                    </TableCell>
                  </TableRow>
                )}

                {!loading &&
                  projects.map((project) => (
                    <TableRow key={project.id} hover>
                      <TableCell>
                        <Typography fontWeight={600}>
                          {project.code} — {project.name}
                        </Typography>
                        {project.description && (
                          <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: 280 }}>
                            {project.description}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell sx={hideOnMobile}>{project.department_name}</TableCell>
                      <TableCell sx={hideOnMobile}>{project.manager_name}</TableCell>
                      <TableCell>
                        <Chip
                          label={project.status.replace('_', ' ')}
                          color={STATUS_COLORS[project.status]}
                          size="small"
                        />
                      </TableCell>
                      <TableCell sx={hideOnMobile}>
                        <Chip
                          label={project.priority}
                          color={PRIORITY_COLORS[project.priority]}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell sx={hideOnTablet}>
                        <Typography
                          variant="body2"
                          color={isOverdue(project) ? 'error' : 'text.primary'}
                          fontWeight={isOverdue(project) ? 600 : 400}
                        >
                          {project.planned_end}
                          {isOverdue(project) ? ' (overdue)' : ''}
                        </Typography>
                      </TableCell>
                      <TableCell align="right" sx={hideOnMobile}>
                        ${Number(project.planned_budget).toLocaleString()}
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title={canEdit ? 'Edit' : 'Requires the Contributor role or higher'}>
                          <span>
                            <IconButton size="small" onClick={() => openEdit(project)} disabled={!canEdit}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title={canDelete ? 'Delete' : 'Requires the Manager role'}>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteTarget(project)}
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

      <ProjectFormDialog
        key={dialogKey}
        open={dialogOpen}
        project={editingProject}
        onClose={() => setDialogOpen(false)}
        onSaved={handleSaved}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={deleting ? undefined : () => setDeleteTarget(null)}>
        <DialogTitle>Delete project?</DialogTitle>
        <DialogContent>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <DialogContentText>
            This permanently deletes <strong>{deleteTarget?.name}</strong>. This cannot be undone.
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
