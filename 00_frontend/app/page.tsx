'use client'

import { FormEvent, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { campaignApi, CampaignBrief, CampaignState, Phase, RunnerMode } from '@/lib/campaign-api'

const phases: Phase[] = ['planning', 'development', 'execution', 'monitoring']
const splitList = (value: string) => value.split(',').map(item => item.trim()).filter(Boolean)
const money = (value: number, currency = 'USD') => new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)

function BriefForm({ onClose, onCreated }: { onClose: () => void; onCreated: (campaign: CampaignState) => void }) {
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
    try { onCreated(await campaignApi.create(brief)) } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create campaign') } finally { setBusy(false) }
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

export default function CampaignDashboard() {
  const [campaigns, setCampaigns] = useState<CampaignState[]>([]); const [selected, setSelected] = useState<CampaignState | null>(null)
  const [runnerMode, setRunnerMode] = useState<RunnerMode | 'offline'>('offline'); const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => { try { const [health, items] = await Promise.all([campaignApi.health(), campaignApi.list()]); setRunnerMode(health.runner_mode); setCampaigns(items); setSelected(current => items.find(item => item.campaign_id === current?.campaign_id) ?? items[0] ?? null) } catch (err) { setRunnerMode('offline'); setError(err instanceof Error ? err.message : 'API unavailable') } }, [])
  useEffect(() => {
    // Loading remote data is the external synchronization performed by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])
  const replace = (campaign: CampaignState) => { setSelected(campaign); setCampaigns(items => [campaign, ...items.filter(item => item.campaign_id !== campaign.campaign_id)]) }
  async function runCampaign() { if (!selected) return; setBusy(true); setError(null); try { replace(await campaignApi.run(selected.campaign_id)) } catch (err) { setError(err instanceof Error ? err.message : 'Run failed') } finally { setBusy(false) } }
  async function decide(decision: 'approved' | 'rejected') { if (!selected) return; const actor = window.prompt('Reviewer name or email'); if (!actor) return; const comment = window.prompt(decision === 'approved' ? 'Approval note (optional)' : 'What needs revision?') ?? undefined; setBusy(true); try { const reviewed = await campaignApi.approve(selected.campaign_id, decision, actor, comment); replace(reviewed); if (decision === 'approved') replace(await campaignApi.run(reviewed.campaign_id)) } catch (err) { setError(err instanceof Error ? err.message : 'Review failed') } finally { setBusy(false) } }
  const awaiting = campaigns.filter(item => item.status === 'awaiting_approval').length
  return <main className="dashboard-shell">
    <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">MC</span><span>Campaign Studio</span></Link><div className={`api-badge ${runnerMode}`}><span /> {runnerMode === 'offline' ? 'API offline' : `${runnerMode} runner`}</div></header>
    <section className="hero-row"><div><p className="eyebrow">AI campaign operations</p><h1>From brief to measurable campaign.</h1><p className="lede">One workspace for strategy, creative development, controlled execution, and performance insight.</p></div><button className="primary-button" onClick={() => setCreating(true)}>New campaign</button></section>
    <section className="metric-grid"><article><span>Total campaigns</span><strong>{campaigns.length}</strong><small>Across the complete lifecycle</small></article><article><span>Awaiting approval</span><strong>{awaiting}</strong><small>Human review stays in control</small></article><article><span>Runner mode</span><strong className="text-value">{runnerMode}</strong><small>{runnerMode === 'adk' ? 'Gemini agent team enabled' : 'Predictable local workflow'}</small></article></section>
    {error && <div className="error-banner"><span>{error}</span><button onClick={() => { setError(null); void load() }}>Retry</button></div>}
    <section className="dashboard-grid">
      <aside className="campaign-list"><div className="section-heading"><div><p className="eyebrow">Campaigns</p><h2>Workspace</h2></div><button className="mini-button" onClick={() => setCreating(true)}>+</button></div>
        {campaigns.length ? campaigns.map(campaign => <button className={`campaign-row ${selected?.campaign_id === campaign.campaign_id ? 'selected' : ''}`} onClick={() => setSelected(campaign)} key={campaign.campaign_id}><span className={`status-dot ${campaign.status}`} /><div><strong>{campaign.brief.brand}</strong><small>{campaign.brief.campaign_goal}</small></div><em>{campaign.status.replaceAll('_', ' ')}</em></button>) : <div className="aside-empty">No campaigns yet.</div>}
      </aside>
      <section className="workspace-card">{selected ? <><div className="campaign-head"><div><p className="eyebrow">{selected.brief.industry || 'Campaign'}</p><h2>{selected.brief.brand}</h2><p>{selected.brief.campaign_goal}</p></div><div className="head-actions"><span>{money(selected.brief.budget, selected.brief.currency)} · {selected.brief.duration_weeks} weeks</span>{selected.status === 'awaiting_approval' ? <><button className="reject-button" disabled={busy} onClick={() => void decide('rejected')}>Request changes</button><button className="approve-button" disabled={busy} onClick={() => void decide('approved')}>Approve & continue</button></> : selected.status !== 'completed' && <button className="primary-button" disabled={busy} onClick={() => void runCampaign()}>{busy ? 'Agents working…' : selected.status === 'draft' ? 'Run campaign' : 'Continue campaign'}</button>}</div></div><PhaseRail campaign={selected} /><OutputPanel campaign={selected} /></> : <div className="empty-state"><div className="empty-icon">✦</div><h3>Shape your first campaign</h3><p>Start with a focused brief. The agent team will plan, develop, prepare, and measure the campaign.</p><button className="secondary-button" onClick={() => setCreating(true)}>Create a campaign</button></div>}</section>
    </section>
    {creating && <BriefForm onClose={() => setCreating(false)} onCreated={campaign => { replace(campaign); setCreating(false) }} />}
  </main>
}
