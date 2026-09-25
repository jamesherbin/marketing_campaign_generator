import { afterEach, expect, it, vi } from 'vitest'
import { campaignApi, CampaignApiError, type CampaignBrief } from '@/lib/campaign-api'
afterEach(() => vi.unstubAllGlobals())
it('001-R5 scopes every campaign operation and leaves discovery unscoped', async () => {
  const fetchMock = vi.fn().mockImplementation(async () => Response.json([])); vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()
  await campaignApi.workspaces(controller.signal)
  await campaignApi.list('A', controller.signal)
  const brief: CampaignBrief = { brand: 'Brand', campaign_goal: 'Goal', target_audience: [], duration_weeks: 4, budget: 100, currency: 'USD', preferred_channels: [], success_metrics: [], constraints: [] }
  await campaignApi.create('A', brief); await campaignApi.run('B', 'id'); await campaignApi.approve('B', 'id', 'approved', 'reviewed')
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/workspaces', '/api/campaigns', '/api/campaigns', '/api/campaigns/id/run', '/api/campaigns/id/execution/approval'])
  expect(fetchMock.mock.calls.map(([, init]) => init.headers['X-Workspace-ID'])).toEqual([undefined, 'A', 'A', 'B', 'B'])
  expect(fetchMock.mock.calls[1][1].signal).toBe(controller.signal)
  expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ brief })
  expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({ decision: 'approved', comment: 'reviewed' })
})
it('preserves denial status for membership refresh', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Unavailable' }, { status: 404 })))
  await expect(campaignApi.list('A')).rejects.toEqual(new CampaignApiError('Unavailable', 404))
})
