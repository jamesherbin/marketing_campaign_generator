// @vitest-environment node
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { GET as workspaces } from '@/app/api/workspaces/route'
import { GET as list, POST as create } from '@/app/api/campaigns/route'
import { POST as action } from '@/app/api/campaigns/[...path]/route'
import { verifyRequestSession, requestSessionCookie } from '@/lib/auth-session'
vi.mock('@/lib/auth-session', () => ({ verifyRequestSession: vi.fn(), requestSessionCookie: vi.fn() }))
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(verifyRequestSession).mockResolvedValue({ uid: 'verified', email: null, name: null, roles: [] })
  vi.mocked(requestSessionCookie).mockReturnValue('verified-cookie')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json([])))
})
afterEach(() => vi.unstubAllGlobals())
function request(path: string, method = 'GET', body?: string) {
  return new NextRequest(`http://localhost/api/${path}`, { method, body, headers: {
    'X-Workspace-ID': 'workspace-a', Authorization: 'Bearer forged',
    'X-User-ID': 'attacker', 'X-Firebase-UID': 'attacker', 'X-Role': 'approver', Cookie: 'arbitrary=secret',
  } })
}
it('001-R1/R2 forwards workspace and only the server-verified session', async () => {
  const response = await list(request('campaigns'))
  expect(response.status).toBe(200)
  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(String(url)).toMatch(/\/api\/v1\/campaigns$/)
  expect(init?.headers).toEqual({ Accept: 'application/json', 'X-Workspace-ID': 'workspace-a', Authorization: 'FirebaseSession verified-cookie' })
  expect(init?.cache).toBe('no-store'); expect(verifyRequestSession).toHaveBeenCalledTimes(1)
})
it('001-R5 discovers workspaces without forwarding a workspace or identity claim', async () => {
  await workspaces(request('workspaces'))
  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(String(url)).toMatch(/\/api\/v1\/workspaces$/)
  expect(init?.headers).toEqual({ Accept: 'application/json', Authorization: 'FirebaseSession verified-cookie' })
})
it.each(['create', 'run', 'approval'])('preserves %s request body and backend status', async operation => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ detail: 'denied' }, { status: 403 }))
  const body = JSON.stringify({ decision: 'approved' })
  const req = request('campaigns', 'POST', body)
  const response = operation === 'create' ? await create(req) : await action(req, { params: Promise.resolve({ path: operation === 'run' ? ['id', 'run'] : ['id', 'execution', 'approval'] }) })
  expect(response.status).toBe(403); expect(await response.json()).toEqual({ detail: 'denied' })
  expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({ method: 'POST', body, headers: { 'X-Workspace-ID': 'workspace-a', 'Content-Type': 'application/json' } })
})
it.each([list, workspaces])('rejects invalid sessions before contacting backend', async handler => {
  vi.mocked(verifyRequestSession).mockRejectedValue(new Error('revoked'))
  expect((await handler(request('campaigns'))).status).toBe(401)
  expect(fetch).not.toHaveBeenCalled()
})
it('rejects missing cookies even when a browser supplies Authorization', async () => {
  vi.mocked(requestSessionCookie).mockReturnValue(null)
  expect((await list(request('campaigns'))).status).toBe(401); expect(fetch).not.toHaveBeenCalled()
})
it('reports backend outage without exposing error details', async () => {
  vi.mocked(fetch).mockRejectedValue(new Error('private connection details'))
  const response = await workspaces(request('workspaces'))
  expect(response.status).toBe(503); expect(await response.json()).toEqual({ detail: 'Backend unavailable' })
})


it('001-R4 middleware returns JSON 401 for sessionless API fetches, but redirects pages', async () => {
  const { proxy } = await import('@/proxy')
  for (const path of ['/api/workspaces', '/api/campaigns', '/api/campaigns/id/run']) {
    const response = proxy(new NextRequest(`http://localhost${path}`))
    expect(response.status).toBe(401)
    expect(await response.json()).toEqual({ detail: 'Authentication required' })
  }
  expect(proxy(new NextRequest('http://localhost/')).status).toBe(307)
})
