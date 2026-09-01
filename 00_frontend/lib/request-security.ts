import { NextRequest } from 'next/server'

export function hasTrustedOrigin(request: NextRequest): boolean {
  const origin = request.headers.get('origin')
  if (!origin) return false

  try {
    const originUrl = new URL(origin)
    const requestUrl = new URL(request.url)
    const trustedOrigins = new Set([requestUrl.origin])
    if (process.env.APP_ORIGIN) trustedOrigins.add(new URL(process.env.APP_ORIGIN).origin)
    return trustedOrigins.has(originUrl.origin)
  } catch {
    return false
  }
}
