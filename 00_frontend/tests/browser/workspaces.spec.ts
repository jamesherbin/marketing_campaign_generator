import { test, expect, type Page, type Route } from '@playwright/test'
import type { CampaignBrief, CampaignState, Workspace, WorkspaceRole } from '../../lib/campaign-api'

const alpha = '11111111-1111-4111-8111-111111111111'
const beta = '22222222-2222-4222-8222-222222222222'
const origin = 'http://127.0.0.1:3100'
const workspace = (id = alpha, role: WorkspaceRole = 'approver'): Workspace => ({
  workspace_id: id, name: id === alpha ? 'Alpha' : 'Beta', slug: id === alpha ? 'alpha' : 'beta', role,
})
function campaign(id = alpha, status: CampaignState['status'] = 'draft'): CampaignState {
  return {
    workspace_id: id, created_by_user_id: '33333333-3333-4333-8333-333333333333',
    campaign_id: id === alpha ? '44444444-4444-4444-8444-444444444444' : '55555555-5555-4555-8555-555555555555',
    version: 1, status, current_phase: status === 'awaiting_approval' ? 'execution' : 'planning',
    brief: { brand: id === alpha ? 'Alpha campaign' : 'Beta campaign', campaign_goal: 'Reach new customers', target_audience: ['Small businesses'], duration_weeks: 4, budget: 1000, currency: 'USD', preferred_channels: ['email'], success_metrics: ['reach'], constraints: [] },
    phase_runs: { planning: { status: status === 'awaiting_approval' ? 'completed' : 'not_started' }, development: { status: status === 'awaiting_approval' ? 'completed' : 'not_started' }, execution: { status: status === 'awaiting_approval' ? 'awaiting_approval' : 'not_started' }, monitoring: { status: 'not_started' } },
    approvals: [], created_at: '2026-09-25T00:00:00Z', updated_at: '2026-09-25T00:00:00Z',
  }
}

// These fixtures intercept only browser HTTP. Production authentication stays intact.
async function fixtures(page: Page, items = [workspace()]) {
  const calls: Array<{ path: string; workspace: string | undefined; method: string; body: unknown }> = []
  const state = { workspaces: items, campaigns: [campaign(), campaign(beta)], denied: false, expired: false }
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.context().addCookies([{ name: 'campaign_session', value: 'browser-test-only-not-a-firebase-session', url: origin, httpOnly: true, sameSite: 'Lax' }])
  await page.route('**/*', async route => {
    const request = route.request(); const url = new URL(request.url())
    // No real Firebase/model/backend services are contacted by this test browser.
    if (url.origin !== origin) return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const selected = request.headers()['x-workspace-id']
    const body = request.postData() ? request.postDataJSON() : undefined
    calls.push({ path: url.pathname, workspace: selected, method: request.method(), body })
    const reply = (json: unknown, status = 200) => route.fulfill({ json, status })
    if (url.pathname === '/api/auth/logout') {
      await page.context().clearCookies()
      return reply({ status: 'signed_out' })
    }
    if (state.expired) return reply({ detail: 'Authentication required' }, 401)
    if (url.pathname === '/api/workspaces') return reply(state.workspaces)
    if (url.pathname === '/api/health') return reply({ status: 'ok', runner_mode: 'deterministic' })
    if (state.denied) return reply({ detail: 'Workspace unavailable' }, 404)
    if (url.pathname === '/api/campaigns' && request.method() === 'GET') return reply(state.campaigns.filter(item => item.workspace_id === selected))
    if (url.pathname === '/api/campaigns' && request.method() === 'POST') {
      const created = campaign(selected); created.brief = body.brief as CampaignBrief
      state.campaigns = [created]; return reply(created, 201)
    }
    const current = state.campaigns.find(item => item.workspace_id === selected && url.pathname.includes(item.campaign_id))
    if (!current) return reply({ detail: 'Not found' }, 404)
    if (url.pathname.endsWith('/execution/approval')) {
      expect(current.status).toBe('awaiting_approval')
      current.status = body.decision === 'approved' ? 'in_progress' : 'failed'
      current.phase_runs.execution.status = body.decision === 'approved' ? 'completed' : 'failed'
      current.approvals.push({ phase: 'execution', decision: body.decision, actor: 'Test approver', actor_firebase_uid: 'test-uid', identity_source: 'firebase_verified', comment: body.comment, decided_at: '2026-09-25T01:00:00Z' })
      return reply(current)
    }
    if (url.pathname.endsWith('/run')) {
      if (!current.approvals.some(item => item.decision === 'approved')) {
        current.status = 'awaiting_approval'; current.current_phase = 'execution'
        current.phase_runs.planning.status = 'completed'; current.phase_runs.development.status = 'completed'; current.phase_runs.execution.status = 'awaiting_approval'
        current.execution = { activities: [{ channel: 'email', action: 'Prepared email draft', status: 'prepared' }], publication_summary: 'Prepared for review; nothing published.' }
      } else {
        current.status = 'completed'; current.current_phase = 'monitoring'; current.phase_runs.monitoring.status = 'completed'
        current.monitoring = { kpis: { reach: null }, analysis: [], recommendations: [], stakeholder_summary: 'Awaiting live analytics.' }
      }
      return reply(current)
    }
    throw new Error(`Unexpected fixture request: ${request.method()} ${url.pathname}`)
  })
  return { state, calls, errors }
}

async function open(page: Page) {
  await page.goto('/')
  await expect(page.getByLabel('Workspace', { exact: true })).toBeVisible()
}
async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true })
}

test('001-R4 unauthenticated navigation reaches the real login page', async ({ page }) => {
  for (const path of ['/api/workspaces', '/api/campaigns']) {
    const response = await page.request.get(path, { maxRedirects: 0 })
    expect(response.status()).toBe(401)
    expect(await response.json()).toEqual({ detail: 'Authentication required' })
  }
  await page.goto('/')
  await expect(page).toHaveURL(/\/login\?returnTo=%2F/)
  await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible()
})

test('001-R5 zero memberships shows access needed and no campaign actions', async ({ page }) => {
  const f = await fixtures(page, []); await open(page)
  await expect(page.getByRole('heading', { name: 'Workspace access needed' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'New campaign' })).toHaveCount(0)
  expect(f.calls.filter(call => call.path.startsWith('/api/campaigns'))).toHaveLength(0)
  expect(f.errors).toEqual([])
})

for (const role of ['viewer', 'editor', 'runner', 'approver'] as const) {
  test(`001-R2 sole ${role} workspace selects automatically and shows only permitted controls`, async ({ page }) => {
    const f = await fixtures(page, [workspace(alpha, role)]); await open(page)
    await expect(page.getByLabel('Workspace', { exact: true })).toHaveValue(alpha)
    await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'New campaign', exact: true })).toHaveCount(role === 'viewer' ? 0 : 1)
    await expect(page.getByRole('button', { name: 'Run campaign', exact: true })).toHaveCount(['runner', 'approver'].includes(role) ? 1 : 0)
    f.state.campaigns[0] = campaign(alpha, 'awaiting_approval')
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Approve & continue' })).toHaveCount(role === 'approver' ? 1 : 0)
    await expect(page.getByRole('button', { name: 'Request changes' })).toHaveCount(role === 'approver' ? 1 : 0)
    expect(f.calls.filter(call => call.path.startsWith('/api/campaigns')).every(call => call.workspace === alpha)).toBe(true)
    expect(f.errors).toEqual([])
    if (role === 'approver') await screenshot(page, 'approval-controls')
  })
}

test('001-R1/R5 multiple workspaces require selection and clear unsaved drafts', async ({ page }) => {
  const f = await fixtures(page, [workspace(), workspace(beta)]); await open(page)
  await expect(page.getByRole('heading', { name: 'Choose a workspace' })).toBeVisible()
  expect(f.calls.filter(call => call.path === '/api/campaigns')).toHaveLength(0)
  await page.getByLabel('Workspace', { exact: true }).selectOption(alpha)
  await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
  await page.getByRole('button', { name: 'New campaign', exact: true }).click()
  await page.getByLabel('Brand', { exact: true }).fill('Private unfinished draft')
  // Close the modal to reach the workspace selector with a real pointer.
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByLabel('Workspace', { exact: true }).selectOption(beta)
  await expect(page.getByRole('heading', { name: 'Beta campaign' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toHaveCount(0)
  await page.getByRole('button', { name: 'New campaign', exact: true }).click()
  await expect(page.getByLabel('Brand', { exact: true })).toHaveValue('')
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  expect(f.errors).toEqual([])
  await screenshot(page, 'switched-workspace')
})

test('001-R1/R5 late run response cannot restore the previous workspace', async ({ page }) => {
  const f = await fixtures(page, [workspace(), workspace(beta)])
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let received!: () => void
  const started = new Promise<void>(resolve => { received = resolve })
  await page.route('**/api/campaigns/*/run', async (route: Route) => {
    received(); await held
    await route.fulfill({ json: { ...campaign(), brief: { ...campaign().brief, brand: 'Late Alpha result' } } })
  })
  await open(page); await page.getByLabel('Workspace', { exact: true }).selectOption(alpha)
  await page.getByRole('button', { name: 'Run campaign', exact: true }).click(); await started
  await page.getByLabel('Workspace', { exact: true }).selectOption(beta)
  await expect(page.getByRole('heading', { name: 'Beta campaign' })).toBeVisible()
  const response = page.waitForResponse('**/api/campaigns/*/run'); release(); await response
  await expect(page.getByRole('heading', { name: 'Beta campaign' })).toBeVisible()
  await expect(page.getByText('Late Alpha result')).toHaveCount(0)
  expect(f.errors).toEqual([])
})

test('001-R2/R3/R5 create, prepare, approve, and monitor through real browser controls', async ({ page }) => {
  const f = await fixtures(page); f.state.campaigns = []; await open(page)
  await page.getByRole('button', { name: 'New campaign', exact: true }).click()
  await page.getByLabel('Brand', { exact: true }).fill('Browser smoke campaign')
  await page.getByLabel('Campaign goal', { exact: true }).fill('Reach new customers')
  await page.getByLabel('Target audiences', { exact: false }).fill('Small businesses')
  await page.getByRole('button', { name: 'Create campaign', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Browser smoke campaign' })).toBeVisible()
  await page.getByRole('button', { name: 'Run campaign', exact: true }).click()
  await expect(page.getByText('Prepared for review; nothing published.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve & continue' })).toBeVisible()
  expect(f.calls.filter(call => call.path.endsWith('/run'))).toHaveLength(1)
  page.once('dialog', dialog => dialog.accept('Reviewed in smoke test'))
  await page.getByRole('button', { name: 'Approve & continue' }).click()
  await expect(page.getByText('Awaiting live analytics.')).toBeVisible()
  await expect(page.getByText('Awaiting data', { exact: true })).toBeVisible()
  expect(f.calls.filter(call => call.path.endsWith('/run'))).toHaveLength(2)
  expect(f.calls.find(call => call.path.endsWith('/execution/approval'))?.body).toEqual({ decision: 'approved', comment: 'Reviewed in smoke test' })
  expect(f.calls.filter(call => call.path.startsWith('/api/campaigns')).every(call => call.workspace === alpha)).toBe(true)
  expect(f.errors).toEqual([])
  await screenshot(page, 'completed-campaign')
})

test('001-R5 membership removal clears campaign data and refreshes discovery', async ({ page }) => {
  const f = await fixtures(page); await open(page)
  await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
  f.state.denied = true; f.state.workspaces = []
  await page.getByRole('button', { name: 'Run campaign', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Workspace access needed' })).toBeVisible()
  await expect(page.getByText('Alpha campaign')).toHaveCount(0)
  expect(f.calls.filter(call => call.path === '/api/workspaces')).toHaveLength(2)
  expect(f.errors).toEqual([])
})

test('001-R4/R5 expired session clears campaign data and navigates to login', async ({ page }) => {
  const f = await fixtures(page); await open(page)
  await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
  f.state.expired = true
  await page.getByRole('button', { name: 'Run campaign', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible()
  await expect(page.getByText('Alpha campaign')).toHaveCount(0)
  expect(f.errors).toEqual([])
})

test('001-R5 logout clears selection and protected page cannot reopen', async ({ page }) => {
  const f = await fixtures(page); await open(page)
  await expect(page.getByRole('heading', { name: 'Alpha campaign' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByText('Alpha campaign')).toHaveCount(0)
  expect(f.calls.filter(call => call.path === '/api/workspaces')).toHaveLength(1)
  await page.goto('/')
  await expect(page).toHaveURL(/\/login\?returnTo=%2F/)
  expect(f.errors).toEqual([])
})


test('003-R1/R2 dashboard and dialog palettes persist through navigation', async ({ page }) => {
  await fixtures(page); await open(page)
  const selector = page.getByRole('combobox', { name: 'Theme' })
  for (const theme of ['light', 'dark']) {
    await selector.selectOption(theme)
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    await page.getByRole('button', { name: 'New campaign', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCSS('background-color', theme === 'light' ? 'rgb(255, 255, 255)' : 'rgb(23, 23, 27)')
    await expect(page.getByLabel('Brand', { exact: true })).toHaveCSS('color', theme === 'light' ? 'rgb(32, 32, 39)' : 'rgb(245, 243, 238)')
    await screenshot(page, `theme-${theme}-dialog`)
    await page.getByRole('button', { name: 'Close', exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.goto('/login')
  await expect(page.getByRole('combobox', { name: 'Theme' })).toHaveValue('dark')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})
