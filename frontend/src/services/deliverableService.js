/**
 * Data access for deliverables-service (backend/deliverables-service).
 * Mirrors its route table exactly:
 *
 *   GET    /deliverables-service                                    list, filterable
 *   GET    /deliverables-service/{id}                                read one
 *   POST   /deliverables-service                                    create
 *   PUT    /deliverables-service/{id}                                update (partial)
 *   DELETE /deliverables-service/{id}                                delete
 *   GET    /deliverables-service/{id}/dependencies                   predecessors + successors
 *   POST   /deliverables-service/{id}/dependencies                   add a predecessor edge
 *   DELETE /deliverables-service/{id}/dependencies/{predecessorId}   remove a predecessor edge
 *
 * api.js already unwraps the {data, meta} envelope onto response.data/.meta,
 * so every function here returns plain values.
 */

import api from './api'

export function listDeliverables(params = {}) {
  return api
    .get('/deliverables-service', { params })
    .then((res) => ({ deliverables: res.data, meta: res.meta }))
}

export function getDeliverable(id) {
  return api.get(`/deliverables-service/${id}`).then((res) => res.data)
}

export function createDeliverable(payload) {
  return api.post('/deliverables-service', payload).then((res) => res.data)
}

export function updateDeliverable(id, payload) {
  return api.put(`/deliverables-service/${id}`, payload).then((res) => res.data)
}

export function deleteDeliverable(id) {
  return api.delete(`/deliverables-service/${id}`)
}

export function listDependencies(id) {
  return api.get(`/deliverables-service/${id}/dependencies`).then((res) => res.data)
}

export function addDependency(id, payload) {
  return api.post(`/deliverables-service/${id}/dependencies`, payload).then((res) => res.data)
}

export function removeDependency(id, predecessorId) {
  return api.delete(`/deliverables-service/${id}/dependencies/${predecessorId}`)
}
