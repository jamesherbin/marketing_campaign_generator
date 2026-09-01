import { NextRequest } from 'next/server'
import { firebaseAdminAuth } from '@/lib/firebase-admin'
import { SESSION_COOKIE_NAME } from '@/lib/auth-constants'

export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 5

export interface AuthenticatedUser {
  uid: string
  email: string | null
  name: string | null
  roles: string[]
}

export async function verifyRequestSession(request: NextRequest): Promise<AuthenticatedUser> {
  const session = request.cookies.get(SESSION_COOKIE_NAME)?.value
  if (!session) throw new Error('Authentication required')

  const claims = await firebaseAdminAuth.verifySessionCookie(session, true)
  const rawRoles = claims.roles
  return {
    uid: claims.uid,
    email: typeof claims.email === 'string' ? claims.email : null,
    name: typeof claims.name === 'string' ? claims.name : null,
    roles: Array.isArray(rawRoles) ? rawRoles.filter((role): role is string => typeof role === 'string') : [],
  }
}

export function requestSessionCookie(request: NextRequest): string | null {
  return request.cookies.get(SESSION_COOKIE_NAME)?.value ?? null
}
