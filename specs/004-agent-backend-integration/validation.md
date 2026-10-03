# 004: Validation history

Spec: [spec.md](spec.md)

These entries are chronological. Statements about pending tasks describe the
state at that entry; the spec contains the final status and evidence summary.

Provider configuration task completed 2026-10-02: `campaign/adk_provider.py`
passes Settings to lazy Gemini clients on cloned agent trees. Tests cover dotenv
keys, key/Vertex precedence, ambient fallback, secret-safe representations, factory
isolation, and API lifespan wiring. The subsequent startup/mapping task is recorded below; remaining requirements
are still pending. No live provider or database validation
was performed for this task.

Factory/startup task completed 2026-10-02 (004-R1, scoped 004-R7): all four
canonical root-agent trees and backend output types are checked, as are all four
deterministic runner types. Tests exercise the real API lifespan and `/health`
with a fake database lifecycle: default deterministic mode, ADK mode without
credentials/client construction, invalid settings, missing agent imports, and
agent construction failures. Failed startup releases the pool and leaves no
initialized runner/mode/database state. The factory now explicitly rejects
unknown modes instead of treating them as ADK. No API contract changed.

Commands run from `00_backend/`:

- `.venv/bin/python -m pytest tests/test_runner_factory.py tests/test_api_startup.py tests/test_adk_provider.py -q`: **21 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **79 passed, 42 deselected**.
- From repository root, `git diff --check`: passed.

No live model calls, real database checks, or container checks were performed;
these tests do not establish provider readiness or complete 004-R7.

Context/isolation task completed 2026-10-02 (004-R2, excluding session cleanup):
`AdkRunnerAdapter` filters a deep campaign copy for both prompt and session state.
Only non-null results from completed phases preceding the requested phase are
exposed. Canonical caller state is unchanged. Tests cover every phase/status
combination, rejected execution retry, retry after invalid output, distinct
session IDs, and overlapping campaigns with intermediate session writes. The
fixtures use the installed ADK in-memory session service and fake events; they
make no model calls.

Commands run from `00_backend/`:

- `.venv/bin/python -m pytest tests/test_adk_context.py tests/test_adk_runner.py -q`: **27 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **102 passed, 42 deselected**.

Session deletion and cancellation cleanup remain the next task; 004-R2 is not
fully complete. No database integration or live provider checks were run.

Session cleanup task completed 2026-10-02 (004-R2, cleanup portion of 004-R5):
all attempts with a returned session ID delete that session in a finally path.
A shielded, awaited deletion task survives repeated caller cancellation without
being detached. Ordinary cleanup exceptions log only the phase and preserve the
result/original error. Creation failure before an ID is returned does not attempt
deletion. The current in-memory deletion implementation is local; no remote
session store or new cleanup timeout policy is introduced. Failed deletion can
leave a session resident and is reported by the safe warning.

Validation from `00_backend/`:

- `.venv/bin/python -m pytest tests/test_adk_cleanup.py tests/test_adk_context.py tests/test_adk_runner.py -q`: **40 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **115 passed, 42 deselected**.
- Repository-root `git diff --check`: passed.

Tests cover successful output, invalid JSON, provider/prompt errors, creation
failure, cancellation during invocation or cleanup, repeated cancellation, and
deletion failure without sensitive logs. Real in-memory ADK session deletion is
verified; no model calls or database integration checks were run. Synthesizer
selection and broader API failure validation remain pending.

Synthesizer selection task completed 2026-10-02 (004-R3 event selection/runtime
validation; 004-R5 adapter failure handling): the adapter defaults to the phase's
`<phase>_synthesizer` author and supports an explicit synthesizer name. It ignores
other authors and partial events, then validates the last matching final response.
Empty or invalid final output does not reuse an earlier valid result. Validation
errors identify only the phase and canonical model, suppressing raw validation
text. Existing session cleanup remains active on all failure paths.

Tests use real ADK Event objects and fake runners for every phase: plain/fenced
JSON, multiple authors, partial events, missing/empty responses, malformed JSON,
prose, arrays, wrong-phase payloads, and invalid nested numbers/UUIDs/dates/KPIs.
They verify caller state is unchanged and cleanup is invoked.

From `00_backend/`:

- `.venv/bin/python -m pytest tests/test_adk_synthesizer.py tests/test_adk_runner.py tests/test_adk_context.py tests/test_adk_cleanup.py -q`: **89 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **164 passed, 42 deselected**.
- Repository-root `git diff --check`: passed.

No model calls or database integration checks were run. Recursive agent/backend
schema parity and active API failure coverage remain pending, so 004-R3/004-R5
are not claimed fully complete.

Recursive contract task completed 2026-10-02 (004-R3 schema compatibility):
`tests/test_agent_contracts.py` replaces the top-level field-name comparison with
recursive validation and serialization schema comparisons for the output schemas
actually attached to all four synthesizers. Only schema-node titles are omitted;
properties, definitions, required fields, types, formats, defaults, and constraints
remain compared. Existing agent/backend models already agree, so no runtime,
frontend, or storage model change was needed.

Representative fixtures round-trip JSON in both directions, including nested
media plans, UUIDs, timestamps, and nullable/mixed-type KPIs. Both sides reject
missing required fields and invalid nested values. Omitted asset IDs generate
fresh UUID4 values and survive cross-validation; omitted status, call-to-action,
and schedule values retain draft/prepared/null semantics. These are runtime
contract checks, not permission to generate measured KPIs without analytics;
004-R6 generation-only checks remain pending.

From `00_backend/`:

- `.venv/bin/python -m pytest tests/test_agent_contracts.py tests/test_agent_imports.py -q`: **31 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **191 passed, 42 deselected**.
- Repository-root `git diff --check`: passed.

No model calls, database checks, or schema migrations were required. The overall
spec remains in progress with prompt alignment and semantic validation still open.

Prompt alignment task completed 2026-10-02 (004-R6 prompt portion): every phase
subagent receives authoritative brief guidance for industry, constraints, budget,
and preferred channels, including a missing-industry fallback. Removed fixed CPG
instructions and references to planning being approved. Planning budget guidance
respects selected channels. Development creative generation now uses the existing
`gemini-2.5-flash` text model and requests draft text assets/written visual
concepts without claiming image generation or storage. Execution preparation and
human approval instructions remain intact. Output schemas and storage are unchanged.

From `00_backend/`:

- `.venv/bin/python -m pytest tests/test_agent_prompts.py tests/test_agent_imports.py tests/test_agent_contracts.py -q`: **37 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **197 passed, 42 deselected**.
- Repository-root `git diff --check`: passed after removing trailing whitespace.

Prompt tests inspect actual configured agents, required guidance, text model
selection, and availability of all referenced state keys in sequence. They do
not prove model compliance or provider availability. No live model calls or
image generation were performed. Runtime status/KPI semantic validation remains
the next task; 004-R6 is not fully implemented.

Generation semantic validation task completed 2026-10-02 (004-R6): the ADK
adapter rejects any asset status other than draft, activity status other than
prepared, missing requested KPI keys, or non-null KPI values (including extra
keys). Pydantic status defaults remain accepted. Empty requested metric lists
and additional null-valued metrics are permitted. Neither model claims nor
campaign metadata establish trusted analytics. Monitoring prompts now explicitly
request these keys/nulls and an explanation that measured data is unavailable.

The checks raise safe AdkRunnerError messages before returning an output and
retain cleanup on rejection. Canonical models are unchanged; tests demonstrate
historical statuses and measured KPI values remain readable. Free-text truth is
not mechanically verified. Active API persistence/502 checks remain a separate
pending task.

From `00_backend/`:

- `.venv/bin/python -m pytest tests/test_adk_semantics.py tests/test_adk_synthesizer.py tests/test_adk_cleanup.py tests/test_agent_prompts.py -q`: **93 passed**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **222 passed, 42 deselected**.
- Repository-root `git diff --check`: passed.

No model calls, database integration checks, schema migrations, or external
publication occurred. Fixtures cover invalid later list entries, exact statuses,
defaults, missing/case-mismatched/duplicate metric names, zero/string/numeric
measurements, extra keys, metadata claims, cleanup, and unchanged input state.

Active API integration task completed 2026-10-03 (004-R4, 004-R5, API portion of
004-R7): `tests/integration/test_adk_api.py` runs the actual API in ADK mode with
real adapters, real ADK in-memory sessions, fake event streams, and PostgreSQL
under restricted runtime grants. The shared API fixture now accepts an optional
runner-mode parameter; existing tests retain deterministic mode. Provider client
construction is blocked during the new scenarios to prohibit model calls.

Seven scenarios cover ordered phases and the approval gate; rejection, fresh
execution retry, renewed approval and verified audit attribution; monitoring;
readback through a fresh API lifespan with fresh adapters; workspace isolation;
provider, malformed-output and semantic failures returning safe 502 responses;
upstream preservation on retry; authentication/role/order checks before agent
invocation; competing runs returning 409; revoked membership preventing commit;
and lock-connection loss returning 503 with session cleanup and explicit retry.
Every recorded ADK session is checked for deletion. No application behavior fix
was required; the existing service passed these integration checks.

Validation on the disposable local PostgreSQL service (commands from
`00_backend/`, with `TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test` for database commands):

- `.venv/bin/python -m pytest tests/integration/test_adk_api.py -q`: **7 passed**.
- `.venv/bin/python -m pytest -m integration -q`: **49 passed, 222 deselected**.
- `.venv/bin/python -m pytest -m 'not integration' -q`: **222 passed, 49 deselected**.
- Repository-root `git diff --check`: passed.

Initial sandboxed database execution was blocked by local socket permissions;
the database checks above passed after approved escalation. The already-running
disposable test service was healthy and left running. Each test removed its own
isolated database and roles. No live model calls, external publication, Cloud SQL
checks, or container import checks occurred. A fresh API lifespan demonstrates
durable readback independent of adapter memory; this is not an OS process-kill
or deployment test. Container verification and final documentation remain open.

Validation/container task completed 2026-10-03 (004-R1–R7 validation): built the
backend from the repository root and verified packaged imports and both runner
modes inside the image. Added reusable `container_smoke.py` alongside this spec;
it imports the API, checks all four canonical agent packages and configured
synthesizers, checks the deterministic default, and prohibits provider client
construction. No Dockerfile or dependency change was needed.

Exact commands from the repository root:

```sh
docker build -f 00_backend/Dockerfile -t campaign-api:spec-004 .
docker run --rm -i --network none --read-only campaign-api:spec-004 python - < specs/004-agent-backend-integration/container_smoke.py
git diff --check
```

Results: image build passed; smoke check passed for deterministic and ADK runners,
API import, packaged agents, and UID 10001. Container had no injected credentials,
no host source mounts, a read-only filesystem, and networking disabled. The built
image manifest list was
`sha256:2c0bfffa09b02047959801ad660fd5df10b31fd4d5303233e4e6aacc8a6dca67`.
The temporary smoke container was removed automatically; the local image remains.
Docker operations required approved sandbox escalation.

Focused/unit and disposable-database evidence from the immediately preceding task
remains applicable: **222 non-integration tests and 49 integration tests passed**.
No application, dependency, or test-suite source changed since those checks; they
were not redundantly rerun for this smoke-script/evidence-only change. This task
completes the container validation gap, not provider readiness or live deployment.
No model calls, full container API startup with database/Firebase, live quality
check, or Cloud SQL deployment was performed. Final documentation/status review
is the remaining checklist task.
