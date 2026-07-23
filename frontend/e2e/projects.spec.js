import { expect, test } from '@playwright/test'

import { fillDate, login, selectOption } from './helpers'

test.describe('Projects CRUD', () => {
  test('creates a project through the UI, then deletes it', async ({ page }) => {
    await login(page)
    await page.goto('/projects')
    await expect(page.getByRole('button', { name: /create project/i })).toBeVisible()

    const suffix = String(Date.now()).slice(-6)
    const code = `E2E${suffix}`
    const name = `E2E Project ${suffix}`

    // --- Create ---
    await page.getByRole('button', { name: /create project/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('Code').fill(code)
    await dialog.getByLabel('Name').fill(name)
    await selectOption(page, dialog, 'Department', /.+/)
    await selectOption(page, dialog, 'Manager', /.+/)
    await fillDate(page, dialog, 'Start Date', '2027-01-01')
    await fillDate(page, dialog, 'Planned End', '2027-12-31')

    await dialog.getByRole('button', { name: /create project/i }).click()

    await expect(page.getByText(`Project "${name}" created`)).toBeVisible()
    const row = page.getByRole('row', { name: new RegExp(code) })
    await expect(row).toBeVisible()

    // --- Delete (cleanup) ---
    await row.getByRole('button').last().click()
    await expect(page.getByText('Delete project?')).toBeVisible()
    await page.getByRole('button', { name: 'Delete' }).click()
    await expect(page.getByText(`Project "${name}" deleted`)).toBeVisible()
    await expect(page.getByRole('row', { name: new RegExp(code) })).toHaveCount(0)
  })
})
