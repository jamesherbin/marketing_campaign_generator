import { NextRequest } from 'next/server'

/** Use the configured public origin so local HTTP works with production images. */
export function usesSecureSessionCookie(request: NextRequest): boolean {
  const origin = process.env.APP_ORIGIN || request.url
  return new URL(origin).protocol === 'https:'
}
