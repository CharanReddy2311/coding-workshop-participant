/**
 * Data access for teams-service (backend/teams-service). Mirrors its route
 * table exactly:
 *
 *   GET    /teams-service        list, filterable via q/department_id/manager_id/is_active
 *   GET    /teams-service/{id}   read one
 *   POST   /teams-service        create
 *   PUT    /teams-service/{id}   update (partial)
 *   DELETE /teams-service/{id}   delete
 *
 * api.js already unwraps the {data, meta} envelope onto response.data/.meta,
 * so every function here returns plain values.
 */

import api from './api'

// Re-exported so the team form can pull department/manager options from the
// same module it already imports CRUD calls from. The actual calls live in
// directoryService.js since projects-service will need the identical
// department_id/manager_id lookups.
export { fetchDepartments, fetchUsers } from './directoryService'

export function listTeams(params = {}) {
  return api.get('/teams-service', { params }).then((res) => ({ teams: res.data, meta: res.meta }))
}

export function getTeam(id) {
  return api.get(`/teams-service/${id}`).then((res) => res.data)
}

export function createTeam(payload) {
  return api.post('/teams-service', payload).then((res) => res.data)
}

export function updateTeam(id, payload) {
  return api.put(`/teams-service/${id}`, payload).then((res) => res.data)
}

export function deleteTeam(id) {
  return api.delete(`/teams-service/${id}`)
}
