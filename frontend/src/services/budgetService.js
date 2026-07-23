/**
 * Data access for budget-service (backend/budget-service). Mirrors its route
 * table:
 *
 *   GET    /budget-service/summary            consumed vs planned, per project
 *   GET    /budget-service/items              list budget items (?project_id=)
 *   POST   /budget-service/items              create a budget item
 *   PUT    /budget-service/items/{id}         update a budget item
 *   DELETE /budget-service/items/{id}         delete a budget item
 *   GET    /budget-service/expenses           list expenses (?project_id=/?budget_item_id=)
 *   POST   /budget-service/expenses           record an expense
 *   DELETE /budget-service/expenses/{id}      delete an expense
 *
 * api.js already unwraps the {data} envelope onto response.data, so every
 * function here returns plain values.
 */

import api from './api'

export function getBudgetSummary() {
  return api.get('/budget-service/summary').then((res) => res.data)
}

export function listBudgetItems(params = {}) {
  return api.get('/budget-service/items', { params }).then((res) => res.data)
}

export function createBudgetItem(payload) {
  return api.post('/budget-service/items', payload).then((res) => res.data)
}

export function updateBudgetItem(id, payload) {
  return api.put(`/budget-service/items/${id}`, payload).then((res) => res.data)
}

export function deleteBudgetItem(id) {
  return api.delete(`/budget-service/items/${id}`)
}

export function listExpenses(params = {}) {
  return api.get('/budget-service/expenses', { params }).then((res) => res.data)
}

export function createExpense(payload) {
  return api.post('/budget-service/expenses', payload).then((res) => res.data)
}

export function deleteExpense(id) {
  return api.delete(`/budget-service/expenses/${id}`)
}
