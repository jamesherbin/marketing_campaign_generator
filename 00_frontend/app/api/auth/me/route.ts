import { NextRequest, NextResponse } from 'next/server'
import { verifyRequestSession } from '@/lib/auth-session'

export async function GET(request: NextRequest) {
  try {
    return NextResponse.json({ user: await verifyRequestSession(request) })
  } catch {
    return NextResponse.json({ detail: 'Authentication required' }, { status: 401 })
  }
}
