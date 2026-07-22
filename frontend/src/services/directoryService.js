/**
 * Read-only reference data for form pickers (department/manager dropdowns).
 * Backed by backend/directory-service — departments and users each lack a
 * dedicated CRUD service, so this is the one place both are listed. Shared
 * across every form that needs a department_id/manager_id foreign key
 * (teams-service today, projects-service next).
 */

import api from './api'

export function fetchDepartments() {
  return api.get('/directory-service/departments').then((res) => res.data)
}

export function fetchUsers() {
  return api.get('/directory-service/users').then((res) => res.data)
}
