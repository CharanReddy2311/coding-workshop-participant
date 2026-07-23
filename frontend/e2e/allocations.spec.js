import { expect, test } from '@playwright/test'

import { fillDate, login, selectOption } from './helpers'

test.describe('Resource allocation', () => {
  // Margaret Hamilton is seeded at exactly 100% today (60% PR01 + 40% PR04).
  // Any further overlapping assignment must be rejected by the sweep-line
  // over-allocation guard, and the UI must surface that conflict.
  test('blocks an assignment that would over-allocate a person', async ({ page }) => {
    await login(page)
    await page.goto('/allocations')
    await expect(page.getByRole('button', { name: /create allocation/i })).toBeVisible()

    await page.getByRole('button', { name: /create allocation/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await selectOption(page, dialog, 'User', /Margaret Hamilton/)
    await selectOption(page, dialog, 'Project', /Data Lakehouse/)
    await dialog.getByLabel('Allocation %').fill('50')
    await fillDate(page, dialog, 'Start Date', '2026-07-01')
    await fillDate(page, dialog, 'End Date', '2026-08-01')

    await dialog.getByRole('button', { name: /create allocation/i }).click()

    // The conflict banner spells out the numbers: "...over-allocate... (existing
    // 100% + requested 50% = 150%, max 100%)".
    await expect(dialog.getByText(/over-allocate/i)).toBeVisible()
    await expect(dialog).toBeVisible() // dialog stays open; nothing was created
  })
})
