import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from '@/app/page'
import { campaignApi, CampaignApiError, type CampaignState, type Workspace, type WorkspaceRole } from '@/lib/campaign-api'
const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => router }))
vi.mock('@/lib/campaign-api', async original => {
  const actual = await original<typeof import('@/lib/campaign-api')>()
  return { ...actual, campaignApi: { workspaces: vi.fn(), list: vi.fn(), health: vi.fn(), create: vi.fn(), run: vi.fn(), approve: vi.fn() } }
})
const ws = (id: string, role: WorkspaceRole = 'approver'): Workspace => ({ workspace_id: id, name: id, slug: id, role })
const campaign = (id: string, status: CampaignState['status'] = 'draft'): CampaignState => ({
  workspace_id: id, campaign_id: `${id}-campaign`, created_by_user_id: 'user', version: 1, status, current_phase: 'planning',
  brief: { brand: `${id} brand`, campaign_goal: 'Goal', target_audience: [], duration_weeks: 4, budget: 100, currency: 'USD', preferred_channels: [], success_metrics: [], constraints: [] },
  phase_runs: { planning: { status: 'not_started' }, development: { status: 'not_started' }, execution: { status: 'not_started' }, monitoring: { status: 'not_started' } },
  approvals: [], created_at: '2026-09-25T00:00:00Z', updated_at: '2026-09-25T00:00:00Z',
})
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const select = (id: string) => fireEvent.change(screen.getByLabelText('Workspace'), { target: { value: id } })
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A')])
  vi.mocked(campaignApi.health).mockResolvedValue({ status: 'ok', runner_mode: 'deterministic' })
  vi.mocked(campaignApi.list).mockImplementation(async id => [campaign(id)])
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('001-R1/R2/R5 workspace dashboard', () => {
  it('shows access needed with zero memberships and no campaign requests', async () => {
    vi.mocked(campaignApi.workspaces).mockResolvedValue([]); render(<Dashboard />)
    await screen.findByText('Workspace access needed')
    expect(campaignApi.list).not.toHaveBeenCalled(); expect(screen.queryByText('New campaign')).toBeNull()
  })
  it('automatically selects a sole workspace', async () => {
    render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' })
    expect(campaignApi.list).toHaveBeenCalledWith('A', expect.any(AbortSignal))
  })
  it('requires selection for multiple memberships and clears drafts when switching', async () => {
    vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A'), ws('B')]); render(<Dashboard />)
    await screen.findByRole('option', { name: 'A · approver' }); expect(campaignApi.list).not.toHaveBeenCalled()
    select('A'); await screen.findByRole('heading', { name: 'A brand' })
    fireEvent.click(screen.getByText('New campaign')); fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Private draft' } })
    select('B'); await screen.findByRole('heading', { name: 'B brand' }); expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByText('New campaign')); expect((screen.getByLabelText('Brand') as HTMLInputElement).value).toBe('')
  })
  it('aborts old list requests and ignores their late responses', async () => {
    const old = deferred<CampaignState[]>(); vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A'), ws('B')])
    vi.mocked(campaignApi.list).mockImplementation(id => id === 'A' ? old.promise : Promise.resolve([campaign(id)]))
    render(<Dashboard />); await screen.findByRole('option', { name: 'A · approver' }); select('A')
    await waitFor(() => expect(campaignApi.list).toHaveBeenCalled()); const signal = vi.mocked(campaignApi.list).mock.calls[0][1]!
    select('B'); await screen.findByRole('heading', { name: 'B brand' }); expect(signal.aborted).toBe(true)
    await act(async () => old.resolve([campaign('A')]))
    expect(screen.queryByText('A brand')).toBeNull()
  })
  it.each(['create', 'run', 'approve'] as const)('ignores late %s results after switching', async operation => {
    const old = deferred<CampaignState>(); vi.mocked(campaignApi[operation]).mockReturnValue(old.promise)
    vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A'), ws('B')])
    vi.mocked(campaignApi.list).mockImplementation(async id => [campaign(id, operation === 'approve' ? 'awaiting_approval' : 'draft')])
    vi.spyOn(window, 'prompt').mockReturnValue('Reviewed')
    render(<Dashboard />); await screen.findByRole('option', { name: 'A · approver' }); select('A'); await screen.findByRole('heading', { name: 'A brand' })
    if (operation === 'create') {
      fireEvent.click(screen.getByText('New campaign')); fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Created' } })
      fireEvent.submit(screen.getByRole('button', { name: 'Create campaign' }).closest('form')!)
    } else fireEvent.click(screen.getByText(operation === 'run' ? 'Run campaign' : 'Approve & continue'))
    expect(campaignApi[operation]).toHaveBeenCalled(); select('B'); await screen.findByRole('heading', { name: 'B brand' })
    await act(async () => old.resolve(campaign('A')))
    expect(screen.queryByText('A brand')).toBeNull()
    if (operation === 'approve') expect(campaignApi.run).not.toHaveBeenCalled()
  })
  it.each(['viewer', 'editor', 'runner', 'approver'] as const)('shows cumulative controls for %s', async role => {
    vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A', role)]); render(<Dashboard />)
    await screen.findByRole('heading', { name: 'A brand' })
    expect(Boolean(screen.queryByText('New campaign'))).toBe(role !== 'viewer')
    expect(Boolean(screen.queryByText('Run campaign'))).toBe(['runner', 'approver'].includes(role))
    cleanup(); vi.mocked(campaignApi.list).mockResolvedValue([campaign('A', 'awaiting_approval')]); render(<Dashboard />)
    await screen.findByRole('heading', { name: 'A brand' })
    expect(Boolean(screen.queryByText('Approve & continue'))).toBe(role === 'approver')
    expect(Boolean(screen.queryByText('Request changes'))).toBe(role === 'approver')
  })
  it.each([403, 404])('clears content and refreshes memberships after %s', async status => {
    vi.mocked(campaignApi.workspaces).mockResolvedValueOnce([ws('A')]).mockResolvedValue([])
    vi.mocked(campaignApi.run).mockRejectedValue(new CampaignApiError('Denied', status)); render(<Dashboard />)
    await screen.findByRole('heading', { name: 'A brand' }); fireEvent.click(screen.getByText('Run campaign'))
    await screen.findByText('Workspace access needed'); expect(screen.queryByText('A brand')).toBeNull()
    expect(campaignApi.workspaces).toHaveBeenCalledTimes(2)
  })
  it('clears campaigns and redirects after session expiry', async () => {
    vi.mocked(campaignApi.run).mockRejectedValue(new CampaignApiError('Expired', 401))
    vi.mocked(campaignApi.workspaces).mockResolvedValueOnce([ws('A')]).mockRejectedValue(new CampaignApiError('Expired', 401))
    render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' }); fireEvent.click(screen.getByText('Run campaign'))
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/login')); expect(screen.queryByText('A brand')).toBeNull()
  })
  it('clears access immediately on logout without rediscovering workspaces', async () => {
    const logout = deferred<Response>(); vi.mocked(fetch).mockReturnValue(logout.promise)
    render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' }); fireEvent.click(screen.getByText('Sign out'))
    expect(screen.queryByText('A brand')).toBeNull()
    await act(async () => logout.resolve(new Response('{}')))
    expect(router.replace).toHaveBeenCalledWith('/login'); expect(campaignApi.workspaces).toHaveBeenCalledTimes(1)
  })
  it('does not restore pending discovery after logout', async () => {
    const discovery = deferred<Workspace[]>(); vi.mocked(campaignApi.workspaces).mockReturnValue(discovery.promise)
    render(<Dashboard />); fireEvent.click(screen.getByText('Sign out'))
    await act(async () => discovery.resolve([ws('A')]))
    expect(campaignApi.list).not.toHaveBeenCalled(); expect(screen.queryByRole('option', { name: 'A · approver' })).toBeNull()
  })
})

it('ignores old mutation denial after switching workspaces', async () => {
  const old = deferred<CampaignState>(); vi.mocked(campaignApi.run).mockReturnValue(old.promise)
  vi.mocked(campaignApi.workspaces).mockResolvedValue([ws('A'), ws('B')])
  render(<Dashboard />); await screen.findByRole('option', { name: 'A · approver' }); select('A')
  await screen.findByRole('heading', { name: 'A brand' }); fireEvent.click(screen.getByText('Run campaign'))
  select('B'); await screen.findByRole('heading', { name: 'B brand' })
  await act(async () => old.reject(new CampaignApiError('Old membership removed', 404)))
  expect(screen.getByRole('heading', { name: 'B brand' })).toBeTruthy()
  expect(campaignApi.workspaces).toHaveBeenCalledTimes(1)
})
it.each(['approved', 'rejected'] as const)('submits %s in the active workspace and only continues approval', async decision => {
  vi.mocked(campaignApi.list).mockResolvedValue([campaign('A', 'awaiting_approval')])
  vi.mocked(campaignApi.approve).mockResolvedValue(campaign('A', decision === 'approved' ? 'in_progress' : 'failed'))
  vi.mocked(campaignApi.run).mockResolvedValue(campaign('A', 'completed'))
  vi.spyOn(window, 'prompt').mockReturnValue('Review note')
  render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' })
  fireEvent.click(screen.getByText(decision === 'approved' ? 'Approve & continue' : 'Request changes'))
  await waitFor(() => expect(campaignApi.approve).toHaveBeenCalledWith('A', 'A-campaign', decision, 'Review note'))
  if (decision === 'approved') await waitFor(() => expect(campaignApi.run).toHaveBeenCalledWith('A', 'A-campaign'))
  else expect(campaignApi.run).not.toHaveBeenCalled()
})
it('keeps content cleared and allows retry when logout fails', async () => {
  vi.mocked(fetch).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(new Response('{}'))
  render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' })
  fireEvent.click(screen.getByText('Sign out')); await screen.findByText('Unable to sign out. Please retry.')
  expect(screen.queryByText('A brand')).toBeNull(); expect(router.replace).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Sign out')); await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/login'))
  expect(campaignApi.workspaces).toHaveBeenCalledTimes(1)
})

it('001-R5 does not rediscover or restore workspaces after session expiry while navigation is pending', async () => {
  vi.mocked(campaignApi.run).mockRejectedValue(new CampaignApiError('Expired', 401))
  // Navigation is mocked and discovery would still succeed: access must stay cleared.
  render(<Dashboard />); await screen.findByRole('heading', { name: 'A brand' })
  fireEvent.click(screen.getByText('Run campaign'))
  await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/login'))
  expect(campaignApi.workspaces).toHaveBeenCalledTimes(1)
  expect(screen.queryByText('A brand')).toBeNull()
  expect(screen.queryByRole('option', { name: 'A · approver' })).toBeNull()
})
