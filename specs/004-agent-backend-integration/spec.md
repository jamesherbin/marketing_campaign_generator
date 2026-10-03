# 004: Agent/backend integration

Status: Implemented (2026-10-03)

## Problem and outcome

Integrate the four phase agents in `agents/` through the authenticated, durable
API in `00_backend/`, with validated outputs and predictable failure behavior.
Implemented and validated within the scope below; live deployment and provider
quality remain separate rollout work.

Pre-change source inspection on 2026-10-02 found the following baseline and gaps
(resolved by this implementation unless listed under remaining limitations):

- `campaign/runner_factory.py` already maps all four root agents to
  `AdkRunnerAdapter`; `main.py` supplies those runners to `CampaignService`.
- The adapter creates in-memory sessions, supplies state and a JSON schema,
  and validates the last nonempty final event. It does not check which subagent
  authored that event or delete sessions after use.
- Agent synthesizers duplicate backend output models. Existing drift tests compare
  only top-level field names, not nested types, defaults, or constraints.
- Execution and monitoring prompts prohibit publication and invented metrics,
  but the runtime models permit arbitrary activity statuses and non-null KPIs.
- Settings read API keys from `.env`, but the runner factory receives only the
  mode; explicit delivery of these settings to the provider is not established.
- Planning prompts hard-code Consumer Packaged Goods despite the brief's optional
  industry. Development prompts call planning “approved,” although planning has
  no human approval gate. Its creative agent uses an image model, but the backend
  asset contract contains text and has no binary artifact storage.

The outcome is one supported integration path, with regression coverage for
existing behavior and implementation of the missing guarantees below. The
[workspace authorization spec](../001-workspace-authorization/spec.md) continues
to govern identity, storage, access, and concurrency. This spec supplements the
[lifecycle baseline](../000-campaign-lifecycle/spec.md).

## Scope

In scope: in-process ADK phase runners, configuration, state handoffs, canonical
output validation, transient session lifecycle, agent instructions, API/storage
regression coverage, and operator documentation.

Out of scope: deploying standalone agent HTTP services, background job queues,
streaming progress, external publishing, analytics ingestion, binary image
storage/generation delivery, new approval stages, model-quality benchmarking,
and frontend redesign. This change does not deploy infrastructure or call models.

## Requirements and acceptance scenarios

### 004-R1: Select and configure all phase runners

The backend must retain `deterministic` as the default and support `adk` for all
four phases. ADK mode must use the canonical package exports below. Invalid mode
or agent construction must fail startup rather than silently use placeholders.
Provider configuration loaded by backend Settings, including `.env` values, must
reach the provider without exposing secrets. Preserve Gemini API-key and Vertex
AI/ambient credential paths; initialization must not make a model request.

- Given no mode override, when runners are built, then all four deterministic
  runners are selected without model calls or model credentials.
- Given ADK mode, when startup constructs runners, then each mapping below is
  present and health reports `adk`; health does not claim provider readiness.
- Given a key supplied only through Settings, when the provider client is built,
  then a stub observes that key; responses and logs do not reveal it.
- Given both API keys, when Gemini is configured, then GOOGLE_API_KEY wins;
  given Vertex mode, then project/location and ADC win over either API key.
- Given repeated factory construction with different settings, then agent package
  exports and process environment remain unchanged and credentials are isolated.
- Given an invalid mode or missing agent package, when startup runs, then it fails
  clearly without switching mode. Failed runner construction must release the
  database pool and leave no initialized runner/health state. Runtime credential
  failures follow 004-R5.

| Phase | Import | Output model in `campaign.models` | Final synthesizer / output key |
| --- | --- | --- | --- |
| planning | `agents.planning_agent.root_agent` | `PlanningOutput` | `planning_synthesizer` / `planning` |
| development | `agents.development_agent.root_agent` | `DevelopmentOutput` | `development_synthesizer` / `development` |
| execution | `agents.execution_agent.root_agent` | `ExecutionOutput` | `execution_synthesizer` / `execution` |
| monitoring | `agents.monitoring_agent.root_agent` | `MonitoringOutput` | `monitoring_synthesizer` / `monitoring` |

### 004-R2: Isolated, explicit phase context

Each attempt must create a fresh session and provide `campaign_state`,
`campaign_brief`, and `<phase>_output` only for completed upstream phases. The
serialized campaign supplied to the model must also exclude stale current or
later phase outputs. Subagents must consume preceding `output_key` results in
sequence. Sessions must be deleted after success, failure, or cancellation;
cleanup failure must not replace the original invocation error or expose data.
Ordinary deletion errors also preserve a successful result and emit a safe
phase-only warning. Cancellation during deletion must wait for the deletion
attempt to finish before propagating cancellation; no deletion task is detached.
If session creation fails before returning an ID, no deletion is attempted.

- Given development after planning, when invoked, then planning data is available
  as `planning_output`, alongside the brief and canonical output schema.
- Given a rejected execution package being retried, when its new session starts,
  then the previous execution package and previous intermediate results are absent.
- Given a non-null upstream result whose phase is not completed, when context is
  built, then neither the prompt nor session state exposes that result. Context
  filtering must not mutate the stored campaign or caller input.
- Given concurrent campaigns or repeated attempts, when agents write intermediate
  state, then no other campaign or attempt receives those values.
- Given success, malformed output, provider failure, or cancellation, when the
  attempt exits, then session deletion is attempted and no intermediate agent
  state is persisted as campaign output.

### 004-R3: Canonical structured final output

Backend Pydantic models remain the runtime authority. Synthesizer schemas must be
compatible recursively, including nested assets/activities, types, defaults, and
constraints. Only the configured final synthesizer's nonempty final text may
supply the phase result. Ignore partial streaming events even if marked final.
If the synthesizer emits multiple final responses, validate the last one; an
empty or invalid last response must not fall back to an earlier valid response.
Validation errors must name the phase/output contract without including model
text or raw validation details. Accept a JSON object or one enclosing JSON Markdown
fence, as supported today; do not recover JSON from arbitrary prose.

- Given earlier subagents emit final responses, when the synthesizer succeeds,
  then only the synthesizer's response is validated and returned.
- Given a missing synthesizer response, malformed JSON, wrong phase payload, or
  invalid nested UUID/date/type, when validation runs, then the attempt fails
  without committing a partial output or falling back to an earlier response.
- Given nested schema drift, when contract checks run, then they detect changes
  to types, required fields, defaults, formats, and constraints in both validation
  and serialization schemas; only cosmetic schema titles are normalized.
- Given omitted asset IDs and optional fields, when either model validates, then
  generated UUIDs and draft/prepared/null defaults retain the same semantics.
- Given valid fixtures for every phase, when serialized and validated across
  agent and backend models, then their contract meanings agree, including defaults.
- Given agent output attempts to supply campaign status or an approval, when
  processed, then it cannot mutate orchestration state or approval history.

### 004-R4: Preserve lifecycle, authorization, and durable commit boundaries

ADK execution must use the existing `CampaignService`, workspace repository,
locking/version checks, and verified identity. Agents return phase outputs only;
they cannot authorize themselves or advance the lifecycle directly.

- Given an authorized runner and a new campaign, when `/run` succeeds, then
  planning and development complete in order and execution stops in
  `awaiting_approval`; monitoring is not called.
- Given an approver records approval, when `/run` is called again, then monitoring
  runs and the campaign completes, retaining server-verified approval provenance.
- Given rejection, when execution is explicitly retried, then a fresh preparation
  package requires another approval before monitoring.
- Given missing authentication, insufficient role, foreign workspace, or invalid
  phase ordering, when execution is requested, then existing 401/403/404/409
  behavior applies and no agent is called.
- Given competing runs or revoked membership during a call, when output is ready,
  then existing locking and access rechecks prevent an unauthorized/duplicate
  commit. A successful output survives a new API lifespan with fresh adapters and
  remains workspace-scoped. Loss of the lock connection cancels the ADK attempt,
  deletes its session, and returns 503; explicit retry uses a fresh session.

### 004-R5: Safe failures and explicit retry

Provider exceptions and invalid outputs must follow the existing phase-failure
path: HTTP 502 and a safe persisted failure message, with upstream results intact
and no automatic phase retry. Database/access failures retain their existing
503/403/404 semantics and may prevent recording a failure. Cancellation must
propagate and release resources; orphaned running phases remain explicitly
retryable after the campaign lock is released.

- Given a provider exception containing a secret or raw prompt, when the API
  returns and state is read, then neither response nor persisted error exposes it.
- Given an invalid output and working database/access, when the call fails, then
  the phase/campaign are failed and later phases have not run.
- Given that failure or an interrupted run, when explicitly retried, then the
  backend creates a new session and resumes the next incomplete phase without
  rerunning completed upstream phases.

### 004-R6: Honest, brief-driven generated artifacts

Agents must use the supplied brief and completed strategy without inventing a
planning approval. Explicit industry and constraints take precedence over generic
role instructions. Development delivers draft text assets; binary media delivery
is outside this contract. Execution remains preparation only, even after approval.
Without an analytics source, monitoring reports every requested success metric
with null and explains that measured performance is unavailable.

The adapter must validate draft asset statuses, prepared activity statuses, and
null/missing KPI rules before accepting output. Status comparisons are exact;
omitted statuses retain Pydantic defaults. Required metric names match the brief
exactly (duplicates require one key); extra metrics are allowed only with null.
An empty requested-metric list permits an empty KPI mapping. Campaign metadata
and model-supplied data do not establish a trusted analytics source. Semantic rejection follows
004-R5. Instructions must prohibit unsupported publication and performance claims;
these checks do not prove the truth of all free-text model content.

- Given an absent industry, then agents use the product and audience context
  without inventing an industry. All subagents must have the brief available and
  treat its industry, constraints, budget, and channel preferences as authoritative.
- Given development, then creative generation uses the existing text-capable
  Gemini model and requests draft text assets or written visual concepts; it must
  not claim image files were generated or stored.
- Given a non-CPG brief, when prompts are constructed, then no instruction imposes
  Consumer Packaged Goods or a nonexistent planning approval.
- Given a development asset marked published or an execution activity marked sent,
  when returned, then it is rejected and no external channel operation occurs.
- Given requested metrics `clicks` and `conversions` with no analytics connector,
  when monitoring returns, then both keys must exist with null values; numeric
  zero or other asserted measurements are rejected, including on additional keys.
- Given execution approval, when state advances, then activities remain prepared;
  approval never implies that publication happened.

### 004-R7: Reproducible verification and supported startup

Ordinary tests must use deterministic runners, fake provider clients, or fake ADK
event streams with no live model calls/cloud credentials. PostgreSQL integration
checks must exercise the active API using fake-backed ADK adapters. The root-context
backend image must include all agents and support imports without standalone
agent services. Document optional live smoke testing separately from acceptance.

- Given the focused suite in a credential-free environment, when executed, then
  all four output contracts, event selection, handoffs, and failures are tested.
- Given the disposable database suite, when the ADK lifecycle fixture runs, then
  approval, persistence, authorization, retry, and isolation checks pass.
- Given a backend image built from the repository root, when agent imports and
  runner construction are checked, then no sibling service or model call is needed.

## Contracts and compatibility

Keep existing routes, request bodies, response models, role requirements, phase
statuses, and error statuses. No database migration or frontend type change is
planned. Persist only canonical validated phase results, never ADK session/event
objects. Adapter-only semantic checks apply to newly generated results and do not
make historical stored campaigns unreadable. Any later canonical schema change
must update frontend types, consumers, database mappings, and this spec together.

The existing per-process runner mode remains the operator control; there is no
client-selected agent, model, or prompt endpoint. The standalone development
agent's FastAPI app and SQLite session store are not the backend integration path.

## Assumptions and open decisions

- Integration means completing and verifying the existing in-process design,
  rather than introducing remote agent services.
- Keep current model identifiers unless the supported text-only development path
  requires a compatible text model. No current provider availability is asserted.
- No blocking product decision remains. Provider wiring and cleanup interfaces
  were checked against the installed locked ADK version.
- Live quality, latency, provider availability, and resource limits remain rollout
  concerns. Background execution and new timeout/retry policies need separate scope.

## Evidence

Final review: 2026-10-03. All checklist tasks are complete. Test paths below are
relative to `00_backend/`. [Detailed validation history](validation.md) preserves
exact commands, dated results, intermediate gaps, and the container image digest.

| Requirement | Evidence | Result |
| --- | --- | --- |
| 004-R1 | `test_adk_provider.py`, `test_runner_factory.py`, `test_api_startup.py`, `test_config.py` | Passed: configuration/precedence, isolation, startup failure and health |
| 004-R2 | `test_adk_context.py`, `test_adk_cleanup.py`, `test_agent_imports.py`, `integration/test_adk_api.py` | Passed: upstream context, session isolation, state handoffs and cancellation cleanup |
| 004-R3 | `test_adk_synthesizer.py`, `test_agent_contracts.py`; service validates only phase outputs | Passed: author selection, nested validation and bidirectional contracts |
| 004-R4 | `integration/test_adk_api.py`, existing `integration/test_api.py` | Passed: ordered phases, approval provenance, durable readback, authorization and locks |
| 004-R5 | `test_adk_cleanup.py`, `test_adk_synthesizer.py`, `integration/test_adk_api.py` | Passed: safe errors, upstream preservation, explicit retry and connection loss |
| 004-R6 | `test_agent_prompts.py`, `test_adk_semantics.py`, `integration/test_adk_api.py` | Passed: prompt constraints, generation-only statuses/null KPIs, unchanged historical schemas |
| 004-R7 | Full unit/integration suites and [container smoke script](container_smoke.py) | 222 non-integration tests and 49 integration tests passed; image build/import checks passed |

The full suites ran on 2026-10-03, and container validation followed on the same
date. The final task changed documentation only; these application/test results
remain applicable. Final whitespace, local-link, requirement-map and checklist
checks passed; no redundant runtime tests were run for documentation edits.

## Remaining limitations and rollout boundaries

- No live provider calls, quality/latency assessment, Cloud SQL validation, or
  deployment occurred. The optional live smoke is not an acceptance prerequisite.
- The container check verifies imports/construction with networking disabled,
  not a full container lifespan with database and Firebase credentials.
- Prompts constrain free-text claims but cannot prove their truth. Human review
  remains necessary. There is no external publishing, binary artifact storage,
  or trusted analytics connector.
- Ordinary cleanup failures preserve the invocation outcome, log a safe warning,
  and may leave an in-memory session resident. Remote session storage, new timeout
  policies, throughput improvements, and durable background jobs remain outside scope.
- API persistence was verified through a fresh application lifespan, not an OS
  process-kill/deployment test. No new schemas, migrations, or frontend contracts
  were introduced.

Configuration and explicit-retry/rollback instructions are in the
[local development guide](../../LOCAL_DEVELOPMENT.md#7-optional-live-model-configuration).
