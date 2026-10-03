# 004: Implementation plan

Spec: [spec.md](spec.md) · Status: completed 2026-10-03

This plan records the implementation approach; final results and limitations are
in the spec and [validation history](validation.md).

## Approach

Extend the existing factory/adapter boundary. Keep `CampaignService` as the only
active lifecycle and persistence coordinator. Do not route the API through the
legacy in-memory orchestrator or standalone development-agent HTTP application.

1. Pass validated provider settings into ADK client/model construction using the
   locked SDK's supported interface. Define and test precedence: Vertex mode uses
   project/location and ADC; otherwise GOOGLE_API_KEY precedes GEMINI_API_KEY,
   then the existing ambient credential path. Avoid global environment mutation.
2. Configure each adapter with its expected synthesizer identity. Filter event
   author/finality, validate canonical JSON, then apply generation-only semantic
   checks. Keep error details out of API responses and persisted state.
3. Build a phase-aware copy of model context containing completed upstream results
   only. Track session creation and delete the session in a cancellation-safe
   finally path. Cleanup errors must be safely diagnosable without raw prompts.
4. Retain agent-local models for standalone import compatibility, with recursive
   schema comparison (normalizing cosmetic schema titles) and cross-validation
   fixtures. This avoids making standalone agents depend on backend import paths.
5. Align agent instructions with brief industry/constraints and actual approval
   semantics. Use text-capable creative generation for draft ContentAsset output;
   do not silently discard generated binary artifacts as if they were stored.
6. Verify the full active API lifecycle with fake-backed adapters and the disposable
   PostgreSQL database. Update operator docs to reflect the verified integration.

## Affected components

| Component/path | Change | Requirement IDs |
| --- | --- | --- |
| `00_backend/campaign/config.py`, `adk_provider.py`, `runner_factory.py`, `main.py` | Explicit settings-to-provider construction and mapping | 004-R1 |
| `00_backend/campaign/adk_runner.py` | Phase context, author selection, semantic checks, cleanup | 004-R2, 004-R3, 004-R5, 004-R6 |
| `agents/*/agent.py`, `agents/development_agent/app/agent.py` | Schemas and brief-driven instructions | 004-R3, 004-R6 |
| `00_backend/campaign/service.py` | Preserve boundaries; change only if integration tests expose a gap | 004-R4, 004-R5 |
| `00_backend/tests/test_adk_runner.py`, `test_agent_imports.py`, `test_runner_factory.py`, `test_config.py` | Credential-free focused coverage | 004-R1–R3, 004-R5–R7 |
| `00_backend/tests/integration/test_api.py` | Fake-backed ADK lifecycle and durable failure tests | 004-R4, 004-R5, 004-R7 |
| Backend Dockerfile and dependency manifests | Verify existing packaging; amend only as required | 004-R7 |
| Root/backend READMEs, `LOCAL_DEVELOPMENT.md`, `.env.example` | Supported configuration and honest limitations | 004-R1, 004-R6, 004-R7 |

## Decisions and dependencies

Backend models remain authoritative; agent-local schemas are guarded by tests.
Semantic restrictions belong at the generation boundary so historical records
remain readable. No migration, UI redesign, or new publication adapter is needed.

Do not replace existing model calls with invented SDK APIs: inspect the installed
locked ADK implementation/docs before coding. Provider credentials are needed only
for an optional operator-run smoke test, not implementation acceptance. The
existing advisory lock is held throughout each phase call; throughput and durable
job scheduling remain outside this change.

## Validation

From `00_backend/`, run these after implementation:

```sh
.venv/bin/python -m pytest tests/test_adk_runner.py tests/test_agent_imports.py tests/test_runner_factory.py tests/test_config.py tests/test_orchestrator.py
.venv/bin/python -m pytest -m 'not integration'
```

Use the [disposable PostgreSQL instructions](../../database/README.md#disposable-postgresql-tests)
for `tests/integration/test_api.py` and related persistence checks. Include all four
fake synthesizer authors, multiple intermediate finals, invalid nested values,
missing output, cancellation, cleanup failure, retries, and concurrent campaigns.
Assert no model requests occur. Map each new test to its requirement ID.

Build the root-context backend image and run agent-import/factory checks without
provider credentials. Record exact commands/results in spec evidence. Optional
live smoke uses a disposable campaign and verifies schema-valid phases stop for
approval; it must never publish and is recorded separately from deterministic tests.

## Rollout and recovery

Keep deterministic as the default. Deploy the same backend/agent revision together,
verify tests and imports, then opt into ADK with server-side credentials. No data
migration is expected. To recover from provider/integration failures, change the
mode back to deterministic and restart; explicitly retry failed phases only after
reviewing that placeholder outputs are acceptable. Completed outputs and audit
history remain intact; mode changes do not imply publication or automatic reruns.

## Locked interface inspection (2026-10-02)

Inspected installed `google-adk==1.25.1` and `google-genai==1.64.0` source.
`Gemini.api_client` is a cached property used by text generation; subclassing it
allows explicit `Client` keyword arguments without changing global environment.
`BaseAgent.clone()` recursively clones subagents and repairs parent links. Models
are replaced only on the cloned trees; private Settings snapshots exclude secrets
from Pydantic serialization. The API uses text generation; ADK's separate live
connection client is outside this integration.

For later tasks, `Event.author` identifies the producer and `is_final_response()`
is not unique to a phase synthesizer. In-memory session deletion is asynchronous:
`delete_session(app_name=..., user_id=..., session_id=...)`. At the time of this inspection these interfaces were only inspected; subsequent
tasks implemented and validated event filtering and cleanup.

## Repeatable container import check

The validation-only script [container_smoke.py](container_smoke.py) runs against
image contents without mounting source or supplying credentials:

```sh
# From the repository root:
docker build -f 00_backend/Dockerfile -t campaign-api:spec-004 .
docker run --rm -i --network none --read-only campaign-api:spec-004 python - < specs/004-agent-backend-integration/container_smoke.py
```

This checks imports and runner construction, not FastAPI lifespan/database startup
or live model availability. Exact execution evidence is in the spec.
