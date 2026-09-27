import { NextRequest, NextResponse } from 'next/server'
import { SESSION_COOKIE_NAME } from '@/lib/auth-constants'
import { usesSecureSessionCookie } from '@/lib/auth-cookie'
import { hasTrustedOrigin } from '@/lib/request-security'

export async function POST(request: NextRequest) {
  if (!hasTrustedOrigin(request)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 })
  }

  const response = NextResponse.json({ status: 'signed_out' })
  response.cookies.set(SESSION_COOKIE_NAME, '', {
    httpOnly: true,
    secure: usesSecureSessionCookie(request),
    sameSite: 'lax',
    maxAge: 0,
    path: '/',
  })
  return response
}
