import { expect, test } from '@playwright/test'

import { login } from './helpers'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('renders the KPI tiles', async ({ page }) => {
    await expect(page.getByText('Active Projects')).toBeVisible()
    await expect(page.getByText('At-Risk Projects').first()).toBeVisible()
    await expect(page.getByText('Over-Allocated People')).toBeVisible()
    await expect(page.getByText('Deliverables Completed')).toBeVisible()
  })

  test('flags the over-budget project in the Budget vs Planned widget', async ({ page }) => {
    const widget = page.locator('.MuiCard-root', { hasText: 'Budget vs Planned' })
    await expect(widget).toContainText('1 over budget')
    await expect(widget).toContainText('PR02 — Customer Portal')
  })

  test('lists at-risk projects from the seeded portfolio', async ({ page }) => {
    const widget = page.locator('.MuiCard-root', {
      hasText: 'Open projects that are past their planned end date',
    })
    await expect(widget).toContainText('PR02 — Customer Portal')
  })
})
