// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const firebaseAdminAuthMock = vi.hoisted(() => ({
  verifyIdToken: vi.fn(),
  createSessionCookie: vi.fn(),
}))

vi.mock('@/lib/firebase-admin', () => ({ firebaseAdminAuth: firebaseAdminAuthMock }))

import { POST as createSession } from '@/app/api/auth/session/route'
import { POST as logout } from '@/app/api/auth/logout/route'

const sessionCookie = 'campaign_session'
const secureAttribute = /;\s*Secure(?:;|$)/i

beforeEach(() => {
  vi.clearAllMocks()
  firebaseAdminAuthMock.verifyIdToken.mockResolvedValue({
    uid: 'test-user',
    email: 'test@example.com',
    auth_time: Math.floor(Date.now() / 1000),
  })
  firebaseAdminAuthMock.createSessionCookie.mockResolvedValue('test-session-cookie')
})

afterEach(() => vi.unstubAllEnvs())

function sessionRequest(origin: string): NextRequest {
  return new NextRequest(`${origin}/api/auth/session`, {
    method: 'POST',
    headers: { origin, 'content-type': 'application/json' },
    body: JSON.stringify({ idToken: 'test-id-token' }),
  })
}

function logoutRequest(origin: string): NextRequest {
  return new NextRequest(`${origin}/api/auth/logout`, {
    method: 'POST',
    headers: { origin },
  })
}

it('002-R7 serializes a Secure session cookie for an HTTPS app origin', async () => {
  vi.stubEnv('APP_ORIGIN', 'https://campaign.example')

  const response = await createSession(sessionRequest('https://campaign.example'))
  const setCookie = response.headers.get('set-cookie') ?? ''

  expect(response.status).toBe(200)
  expect(setCookie).toContain(`${sessionCookie}=test-session-cookie`)
  expect(setCookie).toMatch(secureAttribute)
  expect(setCookie).toMatch(/;\s*HttpOnly(?:;|$)/i)
  expect(setCookie).toMatch(/;\s*SameSite=Lax(?:;|$)/i)
})

it('002-R7 serializes a Secure clearing cookie for an HTTPS app origin', async () => {
  vi.stubEnv('APP_ORIGIN', 'https://campaign.example')

  const response = await logout(logoutRequest('https://campaign.example'))
  const setCookie = response.headers.get('set-cookie') ?? ''

  expect(response.status).toBe(200)
  expect(setCookie).toMatch(new RegExp(`^${sessionCookie}=`))
  expect(setCookie).toMatch(secureAttribute)
  expect(setCookie).toMatch(/;\s*Max-Age=0(?:;|$)/i)
})

it('002-R7 serializes a non-Secure session cookie for local HTTP', async () => {
  vi.stubEnv('APP_ORIGIN', 'http://localhost:3000')

  const response = await createSession(sessionRequest('http://localhost:3000'))
  const setCookie = response.headers.get('set-cookie') ?? ''

  expect(response.status).toBe(200)
  expect(setCookie).toContain(`${sessionCookie}=test-session-cookie`)
  expect(setCookie).not.toMatch(secureAttribute)
})

it('002-R7 serializes a non-Secure clearing cookie for local HTTP', async () => {
  vi.stubEnv('APP_ORIGIN', 'http://localhost:3000')

  const response = await logout(logoutRequest('http://localhost:3000'))
  const setCookie = response.headers.get('set-cookie') ?? ''

  expect(response.status).toBe(200)
  expect(setCookie).not.toMatch(secureAttribute)
  expect(setCookie).toMatch(/;\s*Max-Age=0(?:;|$)/i)
})
