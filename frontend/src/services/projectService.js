/**
 * Data access for projects-service (backend/projects-service). Mirrors its
 * route table exactly:
 *
 *   GET    /projects-service        list, filterable via q/status/priority/
 *                                    department_id/manager_id/start_after/
 *                                    end_before/overdue
 *   GET    /projects-service/{id}   read one
 *   POST   /projects-service        create
 *   PUT    /projects-service/{id}   update (partial)
 *   DELETE /projects-service/{id}   delete
 *
 * api.js already unwraps the {data, meta} envelope onto response.data/.meta,
 * so every function here returns plain values.
 */

import api from './api'

export function listProjects(params = {}) {
  return api.get('/projects-service', { params }).then((res) => ({ projects: res.data, meta: res.meta }))
}

export function getProject(id) {
  return api.get(`/projects-service/${id}`).then((res) => res.data)
}

export function createProject(payload) {
  return api.post('/projects-service', payload).then((res) => res.data)
}

export function updateProject(id, payload) {
  return api.put(`/projects-service/${id}`, payload).then((res) => res.data)
}

export function deleteProject(id) {
  return api.delete(`/projects-service/${id}`)
}
