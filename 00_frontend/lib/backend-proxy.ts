import { NextRequest, NextResponse } from 'next/server'

const API_URL = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080').replace(/\/$/, '')

export async function proxyCampaignRequest(request: NextRequest, suffix = '') {
  try {
    const body = request.method === 'GET' ? undefined : await request.text()
    const response = await fetch(`${API_URL}/api/v1/campaigns${suffix}`, {
      method: request.method, body: body || undefined, cache: 'no-store', signal: AbortSignal.timeout(120_000),
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    })
    const payload = await response.json().catch(() => ({ detail: 'Backend returned an invalid response' }))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ detail: error instanceof Error ? error.message : 'Backend unavailable' }, { status: 503 })
  }
}
