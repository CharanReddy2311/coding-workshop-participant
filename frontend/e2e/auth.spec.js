import { expect, test } from '@playwright/test'

import { ADMIN, login } from './helpers'

test.describe('Authentication', () => {
  test('unauthenticated visitor is redirected to the login page', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('invalid credentials are rejected with an error', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(ADMIN.email)
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page.getByText(/incorrect|unable to log in|invalid/i)).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('valid credentials land on the dashboard, and logout returns to login', async ({ page }) => {
    await login(page, ADMIN)
    await expect(page).toHaveURL('http://localhost:3000/')
    await expect(page.getByText(`Welcome, ${ADMIN.name}`)).toBeVisible()

    await page.getByRole('button', { name: /log out/i }).click()
    await expect(page).toHaveURL(/\/login$/)
  })
})
