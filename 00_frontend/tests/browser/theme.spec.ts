import { test, expect } from '@playwright/test'

test('003-R1/R2 system theme, explicit override, reload, and keyboard access', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/login')
  const root = page.locator('html')
  const selector = page.getByRole('combobox', { name: 'Theme' })
  await expect(root).toHaveAttribute('data-theme', 'light')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(245, 244, 241)')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await selector.selectOption('light')
  await page.reload()
  await expect(selector).toHaveValue('light')
  await expect(root).toHaveAttribute('data-theme', 'light')
  await selector.focus()
  await expect(selector).toBeFocused()
  await selector.press('Tab')
  await expect(selector).not.toBeFocused()
  await selector.selectOption('dark')
  await expect(root).toHaveAttribute('data-theme', 'dark')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(13, 13, 15)')
  await selector.selectOption('system')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(root).toHaveAttribute('data-theme', 'light')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('003-R2 invalid preference falls back to OS', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('campaign-studio-theme', 'invalid'))
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/login')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.getByRole('combobox', { name: 'Theme' })).toHaveValue('system')
})

test('003-R3 blocked storage does not break theme selection', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage blocked') } })
  })
  await page.goto('/login')
  await page.getByRole('combobox', { name: 'Theme' }).selectOption('dark')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('combobox', { name: 'Theme' }).selectOption('light')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  expect(errors).toEqual([])
})


test('003-R2 stored palette initializes before React scripts load', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.addInitScript(() => localStorage.setItem('campaign-studio-theme', 'dark'))
  await page.route('**/_next/**/*.js*', route => route.abort())
  await page.goto('/login')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(13, 13, 15)')
})
