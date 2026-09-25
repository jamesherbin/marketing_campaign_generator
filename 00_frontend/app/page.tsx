'use client'

import { FormEvent, useCallback, useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { campaignApi, CampaignBrief, CampaignState, Phase, RunnerMode, Workspace, CampaignApiError } from '@/lib/campaign-api'

const phases: Phase[] = ['planning', 'development', 'execution', 'monitoring']
const splitList = (value: string) => value.split(',').map(item => item.trim()).filter(Boolean)
const money = (value: number, currency = 'USD') => new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)

function BriefForm({ workspace, onClose, onCreated, onFailure }: { workspace: string; onFailure: (error: unknown) => void; onClose: () => void; onCreated: (campaign: CampaignState) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null)
    const form = new FormData(event.currentTarget)
    const brief: CampaignBrief = {
      brand: String(form.get('brand')), campaign_goal: String(form.get('goal')),
      target_audience: splitList(String(form.get('audience'))), duration_weeks: Number(form.get('duration')),
      budget: Number(form.get('budget')), currency: 'USD', industry: String(form.get('industry')) || undefined,
      product: String(form.get('product')) || undefined, preferred_channels: splitList(String(form.get('channels'))),
      success_metrics: splitList(String(form.get('metrics'))), constraints: splitList(String(form.get('constraints'))),
    }
    try { onCreated(await campaignApi.create(workspace, brief)) } catch (err) { onFailure(err); setError(err instanceof Error ? err.message : 'Unable to create campaign') } finally { setBusy(false) }
  }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="brief-title">
    <div className="modal-head"><div><p className="eyebrow">New campaign</p><h2 id="brief-title">Build the brief</h2></div><button className="icon-button" onClick={onClose} aria-label="Close">×</button></div>
    <form onSubmit={submit} className="brief-form">
      <label>Brand<input name="brand" required placeholder="Acme" /></label><label>Product<input name="product" placeholder="Trailblazer Pro" /></label>
      <label className="span-2">Campaign goal<textarea name="goal" required placeholder="Increase qualified awareness and product consideration" /></label>
      <label className="span-2">Target audiences <small>Comma separated</small><input name="audience" required placeholder="Operations leaders, growing small businesses" /></label>
      <label>Industry<input name="industry" placeholder="Consumer goods" /></label><label>Duration (weeks)<input name="duration" type="number" min="1" max="260" defaultValue="8" required /></label>
      <label>Budget (USD)<input name="budget" type="number" min="1" defaultValue="25000" required /></label><label>Preferred channels<input name="channels" placeholder="social_media, email, digital_ads" /></label>
      <label className="span-2">Success metrics<input name="metrics" placeholder="reach, engagement_rate, conversions" /></label>
      <label className="span-2">Constraints<input name="constraints" placeholder="No unverified claims, human approval before publication" /></label>
      {error && <p className="form-error span-2">{error}</p>}
      <div className="form-actions span-2"><button type="button" className="ghost-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy}>{busy ? 'Creating…' : 'Create campaign'}</button></div>
    </form>
  </section></div>
}

function PhaseRail({ campaign }: { campaign: CampaignState }) {
  return <div className="phase-rail">{phases.map((phase, index) => { const status = campaign.phase_runs[phase].status; return <div className={`phase-step ${status}`} key={phase}><span>{status === 'completed' ? '✓' : index + 1}</span><div><strong>{phase}</strong><small>{status.replaceAll('_', ' ')}</small></div></div> })}</div>
}

function OutputPanel({ campaign }: { campaign: CampaignState }) {
  return <div className="outputs">
    {campaign.planning && <section className="output-card"><p className="eyebrow">Strategy</p><h3>{campaign.planning.positioning_statement}</h3><p>{campaign.planning.value_proposition}</p><div className="tag-row">{campaign.planning.recommended_channels.map(item => <span key={item}>{item.replaceAll('_', ' ')}</span>)}</div><h4>Objectives</h4><ul>{campaign.planning.measurable_objectives.map(item => <li key={item}>{item}</li>)}</ul></section>}
    {campaign.development && <section className="output-card"><p className="eyebrow">Creative development</p><h3>{campaign.development.creative_direction}</h3><div className="asset-list">{campaign.development.assets.map(asset => <article key={asset.asset_id}><small>{asset.channel} · {asset.format}</small><strong>{asset.headline}</strong><p>{asset.body}</p></article>)}</div></section>}
    {campaign.execution && <section className="output-card"><p className="eyebrow">Execution package</p><h3>{campaign.execution.publication_summary}</h3><div className="activity-list">{campaign.execution.activities.map((activity, i) => <div key={`${activity.channel}-${i}`}><span>{activity.status}</span><strong>{activity.channel}</strong><p>{activity.action}</p></div>)}</div></section>}
    {campaign.monitoring && <section className="output-card"><p className="eyebrow">Monitoring</p><h3>{campaign.monitoring.stakeholder_summary}</h3><div className="kpi-grid">{Object.entries(campaign.monitoring.kpis).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value ?? 'Awaiting data'}</strong></div>)}</div><h4>Recommendations</h4><ul>{campaign.monitoring.recommendations.map(item => <li key={item}>{item}</li>)}</ul></section>}
  </div>
}

export default function WorkspaceDashboard() {
  const router = useRouter()
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [active, setActive] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const discovery = useRef<AbortController | null>(null)
  async function logout() {
    discovery.current?.abort()
    setLeaving(true); setActive(''); setWorkspaces(null); setError(null)
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST' })
      if (!response.ok) throw new Error('Unable to sign out. Please retry.')
      router.replace('/login'); router.refresh()
    } catch { setError('Unable to sign out. Please retry.') }
  }
  const sessionExpired = useCallback(() => {
    discovery.current?.abort()
    setLeaving(true); setActive(''); setWorkspaces(null); setError(null)
    router.replace('/login')
  }, [router])
  const refreshAccess = useCallback(() => { setActive(''); setWorkspaces(null); setRefresh(n => n + 1) }, [])
  useEffect(() => {
    if (leaving) return
    const controller = new AbortController()
    discovery.current = controller
    campaignApi.workspaces(controller.signal).then(items => {
      if (controller.signal.aborted) return
      setWorkspaces(items); setError(null)
      setActive(items.length === 1 ? items[0].workspace_id : '')
    }).catch(err => {
      if (controller.signal.aborted) return
      if (err instanceof CampaignApiError && err.status === 401) { sessionExpired(); return }
      setError(err instanceof Error ? err.message : 'Unable to load workspaces')
    })
    return () => controller.abort()
  }, [refresh, leaving, sessionExpired])
  const workspace = workspaces?.find(item => item.workspace_id === active)
  return <>
    <div className="workspace-switcher">
      <label htmlFor="workspace">Workspace</label>
      <select id="workspace" value={active} onChange={event => setActive(event.target.value)} disabled={!workspaces?.length}>
        <option value="">{workspaces === null ? 'Loading workspaces…' : 'Choose a workspace'}</option>
        {workspaces?.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.name} · {item.role}</option>)}
      </select>
    </div>
    {workspace ? <CampaignDashboard key={workspace.workspace_id} workspace={workspace} onAccessChanged={refreshAccess} onLogout={logout} onSessionExpired={sessionExpired} /> :
      <main className="dashboard-shell"><section className="empty-state">
        <h1>{error ? 'Unable to load workspaces' : workspaces === null ? 'Loading…' : workspaces.length ? 'Choose a workspace' : 'Workspace access needed'}</h1>
        <p>{error ?? (workspaces?.length === 0 ? 'Ask an operator to add you to a workspace.' : 'Select your workspace to view its campaigns.')}</p>
        {error && !leaving && <button className="primary-button" onClick={refreshAccess}>Retry</button>}
        <button className="ghost-button" onClick={() => void logout()}>Sign out</button>
      </section></main>}
  </>
}

function CampaignDashboard({ workspace, onAccessChanged, onLogout, onSessionExpired }: { workspace: Workspace; onAccessChanged: () => void; onLogout: () => Promise<void>; onSessionExpired: () => void }) {
  const [campaigns, setCampaigns] = useState<CampaignState[]>([]); const [selected, setSelected] = useState<CampaignState | null>(null)
  const [runnerMode, setRunnerMode] = useState<RunnerMode | 'offline'>('offline'); const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)
  const canCreate = workspace.role !== 'viewer'
  const canRun = workspace.role === 'runner' || workspace.role === 'approver'
  const canApprove = workspace.role === 'approver'
  const failure = useCallback((err: unknown) => {
    if (!alive.current) return
    if (err instanceof CampaignApiError && err.status === 401) { alive.current = false; onSessionExpired(); return }
    if (err instanceof CampaignApiError && [403, 404].includes(err.status)) { onAccessChanged(); return }
    setError(err instanceof Error ? err.message : 'Request failed')
  }, [onSessionExpired, onAccessChanged])
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [health, items] = await Promise.all([campaignApi.health(), campaignApi.list(workspace.workspace_id, signal)])
      if (!alive.current || signal?.aborted) return
      setRunnerMode(health.runner_mode); setCampaigns(items)
      setSelected(current => items.find(item => item.campaign_id === current?.campaign_id) ?? items[0] ?? null)
    } catch (err) { if (!signal?.aborted) failure(err) }
  }, [workspace.workspace_id, failure])
  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    // Fetching remote campaign state is the synchronization performed here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(controller.signal)
    return () => { alive.current = false; controller.abort() }
  }, [load])
  const replace = (campaign: CampaignState) => {
    if (!alive.current || campaign.workspace_id !== workspace.workspace_id) return
    setSelected(campaign); setCampaigns(items => [campaign, ...items.filter(item => item.campaign_id !== campaign.campaign_id)])
  }
  async function runCampaign() {
    if (!selected || !canRun) return
    setBusy(true); setError(null)
    try { replace(await campaignApi.run(workspace.workspace_id, selected.campaign_id)) }
    catch (err) { failure(err) } finally { if (alive.current) setBusy(false) }
  }
  async function decide(decision: 'approved' | 'rejected') {
    if (!selected || !canApprove) return
    const comment = window.prompt(decision === 'approved' ? 'Approval note (optional)' : 'What needs revision?') ?? undefined
    setBusy(true)
    try {
      const reviewed = await campaignApi.approve(workspace.workspace_id, selected.campaign_id, decision, comment)
      if (!alive.current) return
      replace(reviewed)
      if (decision === 'approved') replace(await campaignApi.run(workspace.workspace_id, reviewed.campaign_id))
    } catch (err) { failure(err) } finally { if (alive.current) setBusy(false) }
  }
  async function logout() { alive.current = false; await onLogout() }
  const awaiting = campaigns.filter(item => item.status === 'awaiting_approval').length
  return <main className="dashboard-shell">
    <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">MC</span><span>Campaign Studio</span></Link><div className={`api-badge ${runnerMode}`}><span /> {runnerMode === 'offline' ? 'API offline' : `${runnerMode} runner`}</div><button className="ghost-button" onClick={() => void logout()}>Sign out</button></header>
    <section className="hero-row"><div><p className="eyebrow">AI campaign operations</p><h1>From brief to measurable campaign.</h1><p className="lede">One workspace for strategy, creative development, controlled execution, and performance insight.</p></div>{canCreate && <button className="primary-button" onClick={() => setCreating(true)}>New campaign</button>}</section>
    <section className="metric-grid"><article><span>Total campaigns</span><strong>{campaigns.length}</strong><small>Across the complete lifecycle</small></article><article><span>Awaiting approval</span><strong>{awaiting}</strong><small>Human review stays in control</small></article><article><span>Runner mode</span><strong className="text-value">{runnerMode}</strong><small>{runnerMode === 'adk' ? 'Gemini agent team enabled' : 'Predictable local workflow'}</small></article></section>
    {error && <div className="error-banner"><span>{error}</span><button onClick={() => { setError(null); void load() }}>Retry</button></div>}
    <section className="dashboard-grid">
      <aside className="campaign-list"><div className="section-heading"><div><p className="eyebrow">Campaigns</p><h2>Workspace</h2></div>{canCreate && <button className="mini-button" onClick={() => setCreating(true)}>+</button>}</div>
        {campaigns.length ? campaigns.map(campaign => <button className={`campaign-row ${selected?.campaign_id === campaign.campaign_id ? 'selected' : ''}`} onClick={() => setSelected(campaign)} key={campaign.campaign_id}><span className={`status-dot ${campaign.status}`} /><div><strong>{campaign.brief.brand}</strong><small>{campaign.brief.campaign_goal}</small></div><em>{campaign.status.replaceAll('_', ' ')}</em></button>) : <div className="aside-empty">No campaigns yet.</div>}
      </aside>
      <section className="workspace-card">{selected ? <><div className="campaign-head"><div><p className="eyebrow">{selected.brief.industry || 'Campaign'}</p><h2>{selected.brief.brand}</h2><p>{selected.brief.campaign_goal}</p></div><div className="head-actions"><span>{money(selected.brief.budget, selected.brief.currency)} · {selected.brief.duration_weeks} weeks</span>{selected.status === 'awaiting_approval' ? canApprove && <><button className="reject-button" disabled={busy} onClick={() => void decide('rejected')}>Request changes</button><button className="approve-button" disabled={busy} onClick={() => void decide('approved')}>Approve & continue</button></> : canRun && selected.status !== 'completed' && <button className="primary-button" disabled={busy} onClick={() => void runCampaign()}>{busy ? 'Agents working…' : selected.status === 'draft' ? 'Run campaign' : 'Continue campaign'}</button>}</div></div><PhaseRail campaign={selected} /><OutputPanel campaign={selected} /></> : <div className="empty-state"><div className="empty-icon">✦</div><h3>Shape your first campaign</h3><p>Start with a focused brief. The agent team will plan, develop, prepare, and measure the campaign.</p>{canCreate && <button className="secondary-button" onClick={() => setCreating(true)}>Create a campaign</button>}</div>}</section>
    </section>
    {creating && canCreate && <BriefForm workspace={workspace.workspace_id} onFailure={failure} onClose={() => setCreating(false)} onCreated={campaign => { replace(campaign); setCreating(false) }} />}
  </main>
}
