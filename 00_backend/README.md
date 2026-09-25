# Campaign Orchestrator API

The backend owns the canonical `CampaignState` and advances it through planning,
development, execution, and monitoring. The API persists campaign state in
workspace-scoped PostgreSQL storage and authorizes every request using verified
Firebase identity and active database membership.

## Run locally

From `00_backend/`, after applying [migrations 001–004 and grants](../database/README.md#apply-migrations)
to a dedicated PostgreSQL database and configuring a restricted runtime login:

```bash
uv sync --locked
cp .env.example .env
# Configure runtime DATABASE_URL, GOOGLE_CLOUD_PROJECT, and Firebase Admin ADC.
.venv/bin/uvicorn main:app --reload --port 8080
```

Startup rejects missing/unavailable databases, missing migrations, and inadequate
runtime grants; it never falls back to memory. Configure Firebase Admin ADC for
session verification even in deterministic runner mode. Then use the
[operator runbook](../database/OPERATIONS.md) to create a workspace and assign an
existing Firebase user a role. Configure the frontend with the same Firebase project.

Open `http://localhost:8080/docs` for generated model schemas. `/health` is public
and reports runner mode after successful startup; it is not a live database probe.
The required workspace header is parsed at runtime, so use the contract below
alongside generated OpenAPI documentation.

## Lifecycle

1. `POST /api/v1/campaigns` creates a typed draft.
2. `POST /api/v1/campaigns/{id}/run` runs planning and development, prepares
   execution activities, and stops at the execution approval gate.
3. `POST /api/v1/campaigns/{id}/execution/approval` records a human decision.
4. Call `POST /api/v1/campaigns/{id}/run` again after approval to run monitoring.

Individual phases can instead be invoked through
`POST /api/v1/campaigns/{id}/phases/{phase}/run`. Invalid ordering returns HTTP
409. The built-in runners are deterministic placeholders whose interfaces can be
replaced with Google ADK adapters without changing the API contract.

## API contract

All `/api/v1/workspaces` and campaign routes require a verified Firebase session:
`Authorization: FirebaseSession <session-cookie>`. Raw Google ID tokens, client
UIDs, and token role claims do not establish workspace membership. The frontend
proxy obtains the session from its HTTP-only cookie and forwards it to the API.

`GET /api/v1/workspaces` needs no workspace header and returns active memberships:

```json
[{"workspace_id":"11111111-1111-4111-8111-111111111111","name":"Campaign team","slug":"campaign-team","role":"approver"}]
```

Every campaign route additionally requires `X-Workspace-ID: <UUID>`:

| Method and route | Minimum role | Success |
| --- | --- | --- |
| `GET /api/v1/campaigns` | viewer | 200 campaign array scoped to workspace |
| `GET /api/v1/campaigns/{id}` | viewer | 200 campaign |
| `POST /api/v1/campaigns` | editor | 201 campaign |
| `POST /api/v1/campaigns/{id}/run` | runner | 200 campaign |
| `POST /api/v1/campaigns/{id}/phases/{phase}/run` | runner | 200 campaign |
| `POST /api/v1/campaigns/{id}/execution/approval` | approver | 200 campaign |

Permissions are cumulative. A creator may approve their own campaign if they have
the approver role. Membership is checked on each request and before phase output
commits; switching the dashboard workspace does not cancel work already accepted
by the backend.

Create accepts `{"brief": {...}, "metadata": {}}`; brief fields are defined in
`campaign.models.CampaignBrief`. Approval accepts
`{"decision":"approved","comment":"Reviewed"}` or `"rejected"`, with optional
comment. Both inputs reject extra ownership/actor fields. The server supplies
`workspace_id` and `created_by_user_id` (internal user UUID) on campaign responses.
Approval records expose `actor_firebase_uid` and `identity_source`: new events are
`firebase_verified`, while imported historical displays are `legacy_unverified`
with a null UID. Display text is not proof of historical identity.

| Status | Meaning |
| --- | --- |
| 401 | Missing, invalid, expired, revoked, or unverifiable session |
| 403 | Disabled application user or insufficient role |
| 404 | Missing/inactive workspace membership, unavailable workspace, or missing/foreign campaign |
| 409 | Invalid lifecycle transition, stale version, duplicate approval, or competing run |
| 422 | Invalid payload, phase/ID, or missing/malformed workspace header |
| 502 | Phase runner failed; failure persisted for explicit retry |
| 503 | Database unavailable during a request |

Failures use a `detail` field; validation errors may contain structured details.
Approvals and audit events commit atomically. Phase runs use database advisory
locks and version checks; an interrupted run can be retried explicitly after its
lock is released. Execution prepares activities and does not publish externally.

## ADK runner adapter

`campaign.adk_runner.AdkRunnerAdapter` can replace any deterministic phase
runner. It creates an isolated ADK session, places the serialized campaign in
session state, sends a prompt containing the phase output schema, consumes ADK
events, and validates the final JSON response as the configured Pydantic model.
The session exposes `campaign_brief` plus any completed `planning_output`,
`development_output`, `execution_output`, and `monitoring_output`. Intermediate
subagents add their own `output_key` values for later agents in the same phase.

```python
from agents.planning_agent import root_agent
from campaign.adk_runner import AdkRunnerAdapter
from campaign.models import Phase, PlanningOutput

planning_runner = AdkRunnerAdapter(
    app_name="planning_agent",
    phase=Phase.PLANNING,
    output_model=PlanningOutput,
    agent=root_agent,
)
```

The API constructs runners through `campaign.runner_factory.build_phase_runners`
and passes them to `CampaignService`. The legacy `CampaignOrchestrator` remains
for isolated tests; it is not the active API repository. All four phases must be
present in the runner mapping. Live calls require Gemini API-key or
Vertex AI authentication.

Set `CAMPAIGN_RUNNER_MODE=adk` to make the API invoke the four ADK agents. The
default is `deterministic`, which is safe for local development and tests and
does not make model calls.

```bash
export CAMPAIGN_RUNNER_MODE=adk
export GEMINI_API_KEY="..."  # or configure Vertex AI credentials
.venv/bin/uvicorn main:app --port 8080
```

`GET /health` reports the active runner mode.

## Container and Cloud Run

Build from the repository root:

```bash
docker build -f 00_backend/Dockerfile -t campaign-api:dev .
```

The root build context includes `agents` for ADK mode. The image runs as an
unprivileged user, listens on `PORT`, and contains no credentials. To run it,
supply the same runtime database settings and Firebase ADC as local development.
A host-local PostgreSQL URL must be reachable from inside the container; do not
assume container localhost is the host database.

Before deploying through `cloudbuild.yaml` or Cloud Run, provision private database
connectivity, a dedicated runtime service account with Firebase/Cloud SQL access,
IAM database login, migrations, and runtime grants. Cloud SQL mode uses
`DATABASE_MODE=cloud_sql`, `DATABASE_INSTANCE`, `DATABASE_NAME`, and `DATABASE_USER`
with `DATABASE_URL` unset. Supply `GOOGLE_CLOUD_PROJECT` for Firebase Admin.
See [database infrastructure](../database/README.md) and the
[cutover runbook](../database/OPERATIONS.md); deployment-specific values must be
supplied by the operator. A deploy command containing only runner/project settings
is insufficient for this API.

The frontend proxy currently sends a Firebase session, not a Cloud Run IAM identity
token. Account for that when configuring service ingress and authentication.
Database-backed state is shared across API instances; advisory locks serialize
competing campaign mutations. No deployment or live Cloud SQL validation is
claimed by the local test suite.

## Environment configuration

Configuration is loaded and validated by `campaign.config.Settings`. Values come
from process environment variables, with an optional local `.env` file. Copy
`.env.example` to `.env` for local development; never commit real credentials.
API keys are represented as Pydantic secret values so they are redacted from
settings logs and representations. `OperatorDatabaseSettings` reads only explicit
`OPERATOR_DATABASE_*` process variables; it does not load `.env` or fall back to
the runtime connection. See the [operator runbook](../database/OPERATIONS.md).

## Database implementation and tests

The database connection foundation is available through `DatabaseSettings` and
`campaign.database.database_pool`. Database settings are validated when that
lifecycle starts, with no connections made at import time. Local mode requires
`DATABASE_URL`; Cloud SQL mode requires `DATABASE_INSTANCE`, `DATABASE_NAME`, and
`DATABASE_USER`, and uses private IP with IAM authentication. See `.env.example`.

The PostgreSQL adapter is implemented in `campaign.postgres_repository` with a
workspace-bound asynchronous interface, transactional snapshots, and version checks.
The active API opens its pool in FastAPI lifespan, checks migrations 001–004 and
runtime grants, and uses this adapter through `CampaignService`. The in-memory
repository is retained for isolated tests and legacy migration fixtures.

Use `uv sync --locked` to install runtime and test dependencies. Run unit tests
with `.venv/bin/python -m pytest -m 'not integration'`. See
[database test instructions](../database/README.md#disposable-postgresql-tests)
for the complete suite against an isolated PostgreSQL 16 service.
