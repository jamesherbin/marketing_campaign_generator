import { NextRequest } from 'next/server'
import { proxyCampaignRequest } from '@/lib/backend-proxy'
export const dynamic = 'force-dynamic'
export const GET = (request: NextRequest) => proxyCampaignRequest(request)
export const POST = (request: NextRequest) => proxyCampaignRequest(request)
