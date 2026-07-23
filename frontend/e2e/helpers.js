import { expect } from '@playwright/test'

export const ADMIN = { email: 'admin@acme.example', password: 'ChangeMe!123', name: 'Platform Administrator' }
export const VIEWER = { email: 'barbara.liskov@acme.example', password: 'Passw0rd!' }

/** Log in through the real login form and wait for the dashboard. */
export async function login(page, user = ADMIN) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page.getByText(/^Welcome,/)).toBeVisible()
}

/**
 * Type a yyyy-MM-dd date into a MUI DesktopDatePicker.
 * The v9 field is a role="group" split into year/month/day spinbutton
 * sections; clicking the first section and typing the digits in order
 * auto-advances through the rest.
 */
export async function fillDate(page, scope, label, iso) {
  const [y, m, d] = iso.split('-')
  const group = scope.getByRole('group', { name: label })
  await group.getByRole('spinbutton').first().click()
  await page.keyboard.type(`${y}${m}${d}`)
}

/** Pick an option from a MUI <TextField select> by its label. */
export async function selectOption(page, scope, comboLabel, optionMatcher) {
  await scope.getByRole('combobox', { name: comboLabel }).click()
  await page.getByRole('option', { name: optionMatcher }).first().click()
}
