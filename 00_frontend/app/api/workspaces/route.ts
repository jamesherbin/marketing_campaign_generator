import { NextRequest } from 'next/server'
import { proxyWorkspaceRequest } from '@/lib/backend-proxy'
export const dynamic = 'force-dynamic'
export const GET = (request: NextRequest) => proxyWorkspaceRequest(request)
