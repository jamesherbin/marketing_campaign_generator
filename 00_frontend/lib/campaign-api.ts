export type RunnerMode = 'deterministic' | 'adk'
export type CampaignStatus = 'draft' | 'in_progress' | 'awaiting_approval' | 'completed' | 'failed'
export type Phase = 'planning' | 'development' | 'execution' | 'monitoring'
export type PhaseStatus = 'not_started' | 'running' | 'awaiting_approval' | 'completed' | 'failed'

export interface ApiHealth { status: 'ok'; runner_mode: RunnerMode }
export interface CampaignBrief {
  brand: string; campaign_goal: string; target_audience: string[]; duration_weeks: number
  budget: number; currency: string; preferred_channels: string[]; success_metrics: string[]
  industry?: string; product?: string; constraints: string[]
}
export interface PlanningOutput {
  goals: string[]; measurable_objectives: string[]; audience_segments: string[]
  positioning_statement: string; value_proposition: string; key_messages: string[]
  recommended_channels: string[]; budget_by_channel: Record<string, number>
}
export interface ContentAsset { asset_id: string; channel: string; format: string; headline: string; body: string; call_to_action?: string; status: string }
export interface DevelopmentOutput { creative_direction: string; assets: ContentAsset[]; media_plan: Record<string, unknown> }
export interface ScheduledActivity { channel: string; action: string; scheduled_for?: string; status: string }
export interface ExecutionOutput { activities: ScheduledActivity[]; publication_summary: string }
export interface MonitoringOutput { kpis: Record<string, number | string | null>; analysis: string[]; recommendations: string[]; stakeholder_summary: string }
export interface CampaignState {
  campaign_id: string; version: number; status: CampaignStatus; current_phase: Phase; brief: CampaignBrief
  planning?: PlanningOutput; development?: DevelopmentOutput; execution?: ExecutionOutput; monitoring?: MonitoringOutput
  phase_runs: Record<Phase, { status: PhaseStatus; started_at?: string; completed_at?: string; error?: string }>
  approvals: Array<{ phase: Phase; decision: 'approved' | 'rejected'; actor: string; comment?: string; decided_at: string }>
  created_at: string; updated_at: string
}

export class CampaignApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); this.name = 'CampaignApiError' }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: 'no-store', ...init, headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers } })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new CampaignApiError(payload.detail ?? `Request failed with status ${response.status}`, response.status)
  }
  return response.json() as Promise<T>
}

export const campaignApi = {
  health: () => request<ApiHealth>('/api/health'),
  list: () => request<CampaignState[]>('/api/campaigns'),
  create: (brief: CampaignBrief) => request<CampaignState>('/api/campaigns', { method: 'POST', body: JSON.stringify({ brief }) }),
  run: (id: string) => request<CampaignState>(`/api/campaigns/${id}/run`, { method: 'POST' }),
  approve: (id: string, decision: 'approved' | 'rejected', actor: string, comment?: string) => request<CampaignState>(`/api/campaigns/${id}/execution/approval`, { method: 'POST', body: JSON.stringify({ decision, actor, comment: comment || null }) }),
}
