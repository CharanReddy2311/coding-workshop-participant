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
import TeamFormDialog from '../components/TeamFormDialog'
import { useAuth } from '../context/AuthContext'
import { deleteTeam, listTeams } from '../services/teamService'

export default function Teams() {
  const { hasRole } = useAuth()

  const canCreate = hasRole('MANAGER')
  const canEdit = hasRole('CONTRIBUTOR')
  const canDelete = hasRole('ADMIN')

  const [teams, setTeams] = useState([])
  const [meta, setMeta] = useState({ total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [departmentOptions, setDepartmentOptions] = useState([])

  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)
  const [refreshKey, setRefreshKey] = useState(0)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKey, setDialogKey] = useState(0)
  const [editingTeam, setEditingTeam] = useState(null)
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

  // teams-service has no dedicated departments endpoint, so the filter's
  // option list is derived from whatever teams already reference — fetched
  // once, independent of the active search/filter/pagination below.
  useEffect(() => {
    let cancelled = false
    listTeams({ limit: 200, sort: 'department_id' })
      .then(({ teams: allTeams }) => {
        if (cancelled) return
        const byId = new Map()
        allTeams.forEach((team) => {
          if (team.department_id) byId.set(team.department_id, team.department_name)
        })
        setDepartmentOptions(
          [...byId.entries()]
            .map(([id, name]) => ({ id, name }))
            .sort((a, b) => a.name.localeCompare(b.name)),
        )
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  useEffect(() => {
    let cancelled = false

    async function fetchTeams() {
      setLoading(true)
      setError('')

      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
        sort: 'name',
        order: 'asc',
      }
      if (debouncedSearch) params.q = debouncedSearch
      if (departmentFilter) params.department_id = departmentFilter

      try {
        const { teams: rows, meta: pageMeta } = await listTeams(params)
        if (cancelled) return
        setTeams(rows)
        setMeta(pageMeta)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load teams')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchTeams()
    return () => {
      cancelled = true
    }
  }, [debouncedSearch, departmentFilter, page, rowsPerPage, refreshKey])

  function openCreate() {
    setEditingTeam(null)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function openEdit(team) {
    setEditingTeam(team)
    setDialogKey((key) => key + 1)
    setDialogOpen(true)
  }

  function handleSaved(saved) {
    setDialogOpen(false)
    setSnackbar(`Team "${saved.name}" ${editingTeam ? 'updated' : 'created'}`)
    setRefreshKey((key) => key + 1)
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteTeam(deleteTarget.id)
      setSnackbar(`Team "${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      // Deleting the last row on a page would otherwise strand the view
      // past the new last page.
      if (teams.length === 1 && page > 0) {
        setPage((p) => p - 1)
      } else {
        setRefreshKey((key) => key + 1)
      }
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete team')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppLayout>
      <Box sx={{ maxWidth: 1100, mx: 'auto', p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            Teams
          </Typography>
          <Tooltip title={canCreate ? '' : 'Requires the Manager or Admin role'}>
            <span>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={openCreate}
                disabled={!canCreate}
              >
                Create Team
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
            sx={{ minWidth: 260 }}
          />
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
                  <TableCell>Name</TableCell>
                  <TableCell>Department</TableCell>
                  <TableCell>Manager</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading && (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 5 }}>
                      <CircularProgress size={28} />
                    </TableCell>
                  </TableRow>
                )}

                {!loading && teams.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 5 }}>
                      <Typography color="text.secondary">No teams found.</Typography>
                    </TableCell>
                  </TableRow>
                )}

                {!loading &&
                  teams.map((team) => (
                    <TableRow key={team.id} hover>
                      <TableCell>
                        <Typography fontWeight={600}>{team.name}</Typography>
                        {team.description && (
                          <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: 320 }}>
                            {team.description}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>{team.department_name}</TableCell>
                      <TableCell>{team.manager_name}</TableCell>
                      <TableCell>
                        <Chip
                          label={team.is_active ? 'Active' : 'Inactive'}
                          color={team.is_active ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title={canEdit ? 'Edit' : 'Requires the Contributor role or higher'}>
                          <span>
                            <IconButton size="small" onClick={() => openEdit(team)} disabled={!canEdit}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title={canDelete ? 'Delete' : 'Requires the Admin role'}>
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteTarget(team)}
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

      <TeamFormDialog
        key={dialogKey}
        open={dialogOpen}
        team={editingTeam}
        onClose={() => setDialogOpen(false)}
        onSaved={handleSaved}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={deleting ? undefined : () => setDeleteTarget(null)}>
        <DialogTitle>Delete team?</DialogTitle>
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
