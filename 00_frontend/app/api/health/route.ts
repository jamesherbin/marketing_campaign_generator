import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
  const apiUrl = (
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    'http://localhost:8080'
  ).replace(/\/$/, '')

  try {
    const response = await fetch(`${apiUrl}/health`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: AbortSignal.timeout(5_000),
    })
    const body = await response.json().catch(() => null)

    if (!response.ok) {
      return NextResponse.json(
        { detail: body?.detail ?? `Backend returned status ${response.status}` },
        { status: response.status },
      )
    }

    return NextResponse.json(body)
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Backend is unavailable'
    return NextResponse.json({ detail }, { status: 503 })
  }
}
