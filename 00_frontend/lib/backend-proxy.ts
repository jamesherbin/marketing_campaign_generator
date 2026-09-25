import { NextRequest, NextResponse } from 'next/server'
import { requestSessionCookie, verifyRequestSession } from '@/lib/auth-session'

const API_URL = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080').replace(/\/$/, '')

export const proxyCampaignRequest = (request: NextRequest, suffix = '') => proxyBackendRequest(request, `/campaigns${suffix}`)
export const proxyWorkspaceRequest = (request: NextRequest) => proxyBackendRequest(request, '/workspaces')

async function proxyBackendRequest(request: NextRequest, path: string) {
  try {
    await verifyRequestSession(request)
  } catch {
    return NextResponse.json({ detail: 'Authentication required' }, { status: 401 })
  }

  const sessionCookie = requestSessionCookie(request)
  if (!sessionCookie) return NextResponse.json({ detail: 'Authentication required' }, { status: 401 })

  try {
    const body = request.method === 'GET' ? undefined : await request.text()
    const response = await fetch(`${API_URL}/api/v1${path}`, {
      method: request.method, body: body || undefined, cache: 'no-store', signal: AbortSignal.timeout(120_000),
      headers: {
        Accept: 'application/json',
        ...(path.startsWith('/campaigns') && request.headers.get('X-Workspace-ID') ? { 'X-Workspace-ID': request.headers.get('X-Workspace-ID')! } : {}),
        Authorization: `FirebaseSession ${sessionCookie}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
    })
    const payload = await response.json().catch(() => ({ detail: 'Backend returned an invalid response' }))
    return NextResponse.json(payload, { status: response.status })
  } catch {
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 503 })
  }
}
