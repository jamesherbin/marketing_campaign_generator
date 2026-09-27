import { NextRequest, NextResponse } from 'next/server'
import { firebaseAdminAuth } from '@/lib/firebase-admin'
import { SESSION_MAX_AGE_SECONDS } from '@/lib/auth-session'
import { SESSION_COOKIE_NAME } from '@/lib/auth-constants'
import { usesSecureSessionCookie } from '@/lib/auth-cookie'
import { hasTrustedOrigin } from '@/lib/request-security'

export async function POST(request: NextRequest) {
  if (!hasTrustedOrigin(request)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 })
  }

  const contentType = request.headers.get('content-type') ?? ''
  if (!contentType.toLowerCase().startsWith('application/json')) {
    return NextResponse.json({ detail: 'Content-Type must be application/json' }, { status: 415 })
  }

  try {
    const body = await request.json() as { idToken?: unknown }
    if (typeof body.idToken !== 'string' || body.idToken.length > 10_000) {
      return NextResponse.json({ detail: 'A valid ID token is required' }, { status: 400 })
    }

    const claims = await firebaseAdminAuth.verifyIdToken(body.idToken, true)
    const authAgeSeconds = Math.floor(Date.now() / 1000) - claims.auth_time
    if (authAgeSeconds < 0 || authAgeSeconds > 5 * 60) {
      return NextResponse.json({ detail: 'Recent sign-in required' }, { status: 401 })
    }

    const sessionCookie = await firebaseAdminAuth.createSessionCookie(body.idToken, {
      expiresIn: SESSION_MAX_AGE_SECONDS * 1000,
    })
    const response = NextResponse.json({ user: { uid: claims.uid, email: claims.email ?? null } })
    response.cookies.set(SESSION_COOKIE_NAME, sessionCookie, {
      httpOnly: true,
      secure: usesSecureSessionCookie(request),
      sameSite: 'lax',
      maxAge: SESSION_MAX_AGE_SECONDS,
      path: '/',
    })
    return response
  } catch {
    return NextResponse.json({ detail: 'Unable to establish session' }, { status: 401 })
  }
}
