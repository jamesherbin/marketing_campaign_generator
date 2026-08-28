export interface ApiHealth {
  status: 'ok'
  runner_mode: 'deterministic' | 'adk'
}

interface ApiErrorPayload {
  detail?: string
}

export class CampaignApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'CampaignApiError'
  }
}

export async function checkApiHealth(): Promise<ApiHealth> {
  const response = await fetch('/api/health', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiErrorPayload
    throw new CampaignApiError(
      payload.detail ?? `API health check failed with status ${response.status}`,
      response.status,
    )
  }

  return response.json() as Promise<ApiHealth>
}
