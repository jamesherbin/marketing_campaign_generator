import { NextRequest } from 'next/server'
import { proxyCampaignRequest } from '@/lib/backend-proxy'
export const dynamic = 'force-dynamic'
type Context = { params: { path: string[] } }
export const GET = (request: NextRequest, { params }: Context) => proxyCampaignRequest(request, `/${params.path.join('/')}`)
export const POST = (request: NextRequest, { params }: Context) => proxyCampaignRequest(request, `/${params.path.join('/')}`)
