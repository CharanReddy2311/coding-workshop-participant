/**
 * Data access for allocations-service (backend/allocations-service). Mirrors
 * its route table exactly:
 *
 *   GET    /allocations-service        list, filterable via user_id/project_id
 *   GET    /allocations-service/{id}   read one
 *   POST   /allocations-service        create
 *   PUT    /allocations-service/{id}   update (partial)
 *   DELETE /allocations-service/{id}   delete
 *
 * The backend takes/returns plain start_date/end_date (never the underlying
 * Postgres daterange), so payloads here look exactly like every other
 * dated resource in this app.
 *
 * api.js already unwraps the {data, meta} envelope onto response.data/.meta,
 * so every function here returns plain values.
 */

import api from './api'

export function listAllocations(params = {}) {
  return api
    .get('/allocations-service', { params })
    .then((res) => ({ allocations: res.data, meta: res.meta }))
}

export function getAllocation(id) {
  return api.get(`/allocations-service/${id}`).then((res) => res.data)
}

export function createAllocation(payload) {
  return api.post('/allocations-service', payload).then((res) => res.data)
}

export function updateAllocation(id, payload) {
  return api.put(`/allocations-service/${id}`, payload).then((res) => res.data)
}

export function deleteAllocation(id) {
  return api.delete(`/allocations-service/${id}`)
}
