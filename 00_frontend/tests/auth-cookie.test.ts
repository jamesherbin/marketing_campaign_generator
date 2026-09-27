// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { usesSecureSessionCookie } from '@/lib/auth-cookie'

afterEach(() => vi.unstubAllEnvs())

it('002-R7 omits Secure for a configured local HTTP origin even in the production image', () => {
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('APP_ORIGIN', 'http://localhost:3000')
  expect(usesSecureSessionCookie(new NextRequest('http://localhost:3000/api/auth/session'))).toBe(false)
})

it('002-R7 marks session cookies Secure for a configured HTTPS origin', () => {
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('APP_ORIGIN', 'https://campaign.example')
  expect(usesSecureSessionCookie(new NextRequest('http://internal:3000/api/auth/session'))).toBe(true)
})

it.each([
  ['http://localhost:3000', false],
  ['https://campaign.example', true],
])('002-R7 derives the cookie flag from the request origin when APP_ORIGIN is unset', (url, expected) => {
  vi.stubEnv('APP_ORIGIN', '')
  expect(usesSecureSessionCookie(new NextRequest(`${url}/api/auth/session`))).toBe(expected)
})
