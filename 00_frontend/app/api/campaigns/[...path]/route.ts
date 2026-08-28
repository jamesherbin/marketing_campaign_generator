import { NextRequest } from 'next/server'
import { proxyCampaignRequest } from '@/lib/backend-proxy'
export const dynamic = 'force-dynamic'
type Context = { params: Promise<{ path: string[] }> }

async function proxyRequest(request: NextRequest, { params }: Context) {
  const { path } = await params
  return proxyCampaignRequest(request, `/${path.join('/')}`)
}

export const GET = proxyRequest
export const POST = proxyRequest
