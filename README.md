# Marketing Campaign Generator

An end-to-end campaign workspace built around a shared `CampaignState` contract. A FastAPI orchestrator advances campaigns through planning, development, execution approval, and monitoring; Google ADK agents can supply phase outputs; and a Next.js dashboard provides the operator interface.

## Architecture

```mermaid
flowchart LR
    UI[Next.js dashboard] -->|same-origin proxy| API[FastAPI orchestrator]
    API --> STATE[Workspace-scoped PostgreSQL repository]
    API --> RUNNERS{Runner mode}
    RUNNERS -->|deterministic| FIXTURES[Local placeholder runners]
    RUNNERS -->|adk| AGENTS[Google ADK agents]
    AGENTS --> PLAN[Planning]
    PLAN --> DEV[Development]
    DEV --> EXEC[Execution]
    EXEC -->|human approval| MON[Monitoring]
```

| Directory | Purpose |
| --- | --- |
| `00_frontend/` | Next.js 16 campaign dashboard and backend proxy routes |
| `00_backend/` | FastAPI API, `CampaignState` models, orchestration, runners, and tests |
| `agents/` | Importable Google ADK agents for each campaign phase |

Campaign state persists in PostgreSQL across backend restarts. Firebase sessions
identify users; active database memberships determine workspace access and roles.

## Campaign lifecycle

1. Create a typed campaign brief.
2. Run planning and development.
3. Prepare execution activities and pause at the human approval gate.
4. Approve or reject execution.
5. Continue an approved campaign into monitoring.

Use the **Theme** selector on login or in workspace navigation to choose Light, Dark, or System. System follows your device appearance; your selection is saved in this browser.

The dashboard displays campaign status, phase progress, strategy, creative assets, execution activities, approvals, KPIs, and recommendations.

## Prerequisites

- Python 3.11 or newer and uv
- Node.js 20 or newer and Bun 1.3 or newer
- PostgreSQL 16 with migrations 001–004 and separate runtime/operator grants
- A Firebase project with Google sign-in enabled, frontend public configuration,
  and Application Default Credentials (ADC) for both servers
- A Gemini API key or Vertex AI credentials when using ADK mode

## Set up the backend Python environment

From the repository root, use `uv` to create the backend virtual environment and
install the locked runtime and development dependencies:

```bash
cd 00_backend
uv sync --locked
.venv/bin/python --version
cd ..
```

`uv sync --locked` creates `00_backend/.venv` if needed and installs the versions
recorded in `uv.lock`. Re-run it after dependency or lockfile changes. The startup
commands below use executables from `.venv`, so activating the environment is not
required.

## Run locally

Choose the Docker stack for a complete local setup, or run the backend and frontend
in separate terminals for automatic reload during development. Both paths need a
persistent PostgreSQL database, Firebase Google sign-in, and Google Application
Default Credentials (ADC). Deterministic mode avoids model calls, but still needs
database access and Firebase authentication.

### One-time setup

1. Enable Google sign-in and authorize `localhost` in your Firebase project. Use
   that project's web-app configuration for the frontend and the same project ID
   for both servers. The example files contain a project configuration; confirm it
   is the project you intend to use.
2. Configure ADC for the servers, for example with
   `gcloud auth application-default login`. If using a credential file instead,
   export `GOOGLE_APPLICATION_CREDENTIALS` with its absolute path in each server
   terminal. Keep the credential file outside the repository.
3. Prepare environment files using the instructions for your chosen path below.
   Copy examples only when a local file does not already exist.

### Option A: Run the complete Docker stack

Install and start Docker with Compose. From the repository root:

```bash
[ -f .env ] || cp .env.example .env
```

Edit the root `.env`: replace all four password placeholders with distinct,
URL-safe values (generate each with `openssl rand -hex 24`), set `LOCAL_APP_UID`
to the output of `id -u`, and set `GOOGLE_APPLICATION_CREDENTIALS_HOST` to the
absolute path of your ADC file. Check the Firebase project and web-app values.
For gcloud user ADC, the usual file is
`~/.config/gcloud/application_default_credentials.json`; expand `~` in the setting.

Then start the persistent database, apply migrations and grants, and start both
application servers:

```bash
docker compose -f compose.local.yaml up -d --wait postgres
docker compose -f compose.local.yaml run --rm migrate
docker compose -f compose.local.yaml up -d --build --wait api frontend
docker compose -f compose.local.yaml ps
```

The frontend is at <http://localhost:3000>, backend health at
<http://localhost:8080/health>, and API documentation at
<http://localhost:8080/docs>. Compose configures the frontend's internal backend
URL as `http://api:8080` and runs deterministic agents. Its environment comes from
the root `.env`, not the two native-development files below.

Use these commands from the repository root to inspect or stop the stack:

```bash
docker compose -f compose.local.yaml logs -f api frontend
docker compose -f compose.local.yaml stop
# Resume stopped services:
docker compose -f compose.local.yaml start
```

Stopping preserves database data. After source changes, rerun the `up -d --build
--wait api frontend` command to rebuild. For configuration details, see the
[Docker Compose quick start](LOCAL_DEVELOPMENT.md#docker-compose-quick-start).

### Option B: Run backend and frontend with automatic reload

Use Python 3.11+, uv, Node.js 20+, and Bun 1.3+. You can use the persistent Compose
PostgreSQL service: configure the root `.env` as above, then run only the
`postgres` and `migrate` commands. It is available to host processes on port
**5433**. An existing PostgreSQL installation also works after applying
[migrations 001–004 and runtime/operator grants](database/README.md#apply-migrations).
Do not use the disposable integration-test database on port 55432 for campaigns.

If the Compose application servers are running, stop them before starting native
servers on the same ports:

```bash
docker compose -f compose.local.yaml stop api frontend
```

**Terminal 1 — backend**, starting from the repository root:

```bash
cd 00_backend
[ -f .env ] || cp .env.example .env
```

Edit `00_backend/.env` before launching. For the Compose database, use:

```dotenv
CAMPAIGN_RUNNER_MODE=deterministic
DATABASE_MODE=local
DATABASE_URL=postgresql://campaign_runtime:YOUR_RUNTIME_PASSWORD@127.0.0.1:5433/campaigns
GOOGLE_CLOUD_PROJECT=YOUR_FIREBASE_PROJECT_ID
```

Replace the password with `LOCAL_CAMPAIGN_RUNTIME_PASSWORD` from the root `.env`
and use your Firebase project ID. For another database, use its actual runtime
URL. The API never applies migrations automatically or falls back to memory.

With ADC configured in this terminal, start the API from `00_backend/`:

```bash
.venv/bin/uvicorn main:app --reload --port 8080
```

**Terminal 2 — frontend**, starting from the repository root:

```bash
cd 00_frontend
bun install --frozen-lockfile
[ -f .env.local ] || cp .env.example .env.local
```

Edit `00_frontend/.env.local`: set `API_URL=http://localhost:8080`,
`APP_ORIGIN=http://localhost:3000`, and `GOOGLE_CLOUD_PROJECT` to the backend's
Firebase project. Set all five `NEXT_PUBLIC_FIREBASE_*` values from that project's
registered web app. Model keys and server credentials must not use a
`NEXT_PUBLIC_*` variable. Configure ADC for this terminal too, then start:

```bash
bun run dev
```

Open <http://localhost:3000>. Browser requests go to same-origin Next.js `/api`
routes, which forward them to the backend using the server-only `API_URL`.
Use Ctrl+C in each terminal to stop the servers. Restart after environment changes.

### Verify startup and provision access

From another terminal:

```bash
curl http://localhost:8080/health
```

The default response is `{"status":"ok","runner_mode":"deterministic"}`.
This confirms startup and runner selection, not live provider readiness.

Sign in at <http://localhost:3000>. A Firebase login alone grants no workspace
access. For a new installation, use the
[workspace provisioning steps](LOCAL_DEVELOPMENT.md#6-provision-workspace-membership)
(or the [Compose provisioning commands](LOCAL_DEVELOPMENT.md#docker-compose-quick-start))
to create a workspace with `campaign.manage workspace-create` and explicitly
assign your Firebase UID using `campaign.manage member-set --role approver`.
Use separate operator database credentials; the workspace creator does not
automatically receive membership. The approver role permits the full local workflow.

After membership is assigned, refresh and select your workspace. Create a brief,
run the campaign to the execution approval gate, review and approve the prepared
activities, then run again to complete monitoring. For real model output, follow
[Runner modes](#runner-modes); the checked-in Compose stack fixes its mode to
`deterministic`, so use the native backend instructions for the ADK example below.

## Runner modes

The backend defaults to deterministic runners. They generate schema-valid placeholder results without model calls, making local development and tests reproducible.

To call the agents in `agents/`, enable ADK mode and provide authentication:

```bash
cd 00_backend
export CAMPAIGN_RUNNER_MODE=adk
export GEMINI_API_KEY=your-key
.venv/bin/uvicorn main:app --reload --port 8080
```

These settings can also be set in `00_backend/.env`. `GOOGLE_API_KEY` takes
precedence over `GEMINI_API_KEY` if both are configured. For Vertex AI, set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`, then configure Application Default Credentials.

The ADK runner adapter:

- creates an isolated session for each phase run;
- supplies campaign context containing only completed upstream phase outputs;
- requests the phase's JSON schema;
- validates only the designated synthesizer's final response against the canonical output model;
- rejects non-draft assets, non-prepared activities, and non-null KPIs or missing requested metrics;
- deletes each attempt's session after success, failure, or cancellation.

`GET /health` reports the active runner mode, not provider readiness. Vertex mode
uses project/location and ADC ahead of API keys. See the
[live configuration and recovery guide](LOCAL_DEVELOPMENT.md#7-optional-live-model-configuration)
and [integration evidence](specs/004-agent-backend-integration/spec.md#evidence).

## API

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/health` | Service health and runner mode |
| `GET` | `/api/v1/workspaces` | Discover active memberships and roles |
| `POST` | `/api/v1/campaigns` | Create a campaign |
| `GET` | `/api/v1/campaigns` | List campaigns |
| `GET` | `/api/v1/campaigns/{id}` | Get campaign state |
| `POST` | `/api/v1/campaigns/{id}/run` | Advance until complete or blocked by approval |
| `POST` | `/api/v1/campaigns/{id}/phases/{phase}/run` | Run one valid phase |
| `POST` | `/api/v1/campaigns/{id}/execution/approval` | Approve or reject execution |

Workspace/campaign endpoints require `Authorization: FirebaseSession <session>`.
Campaign endpoints also require `X-Workspace-ID: <UUID>`. The frontend proxy supplies
the verified session and selected workspace. Roles are cumulative: viewer reads,
editor creates, runner executes phases, and approver records decisions.

See [backend API contracts](00_backend/README.md#api-contract) for request bodies,
ownership and approval provenance, and error statuses. Invalid lifecycle or
concurrent transitions return `409`.

## Configuration

Backend variables are loaded and validated by `campaign.config.Settings` from the process environment and an optional `00_backend/.env` file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_MODE` | `local` | `local` URL or private `cloud_sql` IAM connection |
| `DATABASE_URL` | unset | Required runtime PostgreSQL URL in local mode |
| `DATABASE_INSTANCE` / `DATABASE_NAME` / `DATABASE_USER` | unset | Required in Cloud SQL mode; URL must be unset |
| `CAMPAIGN_RUNNER_MODE` | `deterministic` | Select `deterministic` or `adk` runners |
| `PORT` | `8080` | Backend port when running `main.py` |
| `LOG_LEVEL` | `info` | Backend logging level |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | unset | Gemini authentication for ADK mode |
| `GOOGLE_GENAI_USE_VERTEXAI` | `false` | Use Vertex AI instead of the Gemini API |
| `GOOGLE_CLOUD_PROJECT` | unset | Firebase Admin project; also used by Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region |
| `API_URL` | `http://localhost:8080` | Server-side backend URL used by the frontend proxy |

See [backend configuration](00_backend/.env.example) and
[frontend configuration](00_frontend/.env.example). Operator commands use explicit
`OPERATOR_DATABASE_*` process settings, not the API connection or `.env`. Do not
commit secrets. Browser Firebase configuration is public; model API keys and
service-account credentials remain server-side.

## Tests and builds

Changes follow the [spec-driven development workflow](specs/README.md): define
requirements and acceptance scenarios, plan the implementation, then record
validation evidence alongside the code. Start with the
[workspace authorization spec](specs/001-workspace-authorization/spec.md). The
[lifecycle baseline](specs/000-campaign-lifecycle/spec.md) records historical behavior.

Run backend tests:

```bash
cd 00_backend
uv sync --locked
.venv/bin/python -m pytest -m 'not integration'
```

For the full suite, including PostgreSQL migration tests, follow the
[disposable database test instructions](database/README.md#disposable-postgresql-tests).

Validate the frontend (run build and browser checks sequentially):

```bash
cd 00_frontend
bun run test
bun run lint
bun run build
bunx playwright install chromium --only-shell
bun run test:browser
```

## Current limitations

- Workspace/membership administration uses operator commands; there is no invitation or administration UI.
- Deterministic runners are placeholders, not live channel integrations.
- Execution prepares publication activities but does not publish to external advertising, email, or social platforms.
- Monitoring returns an empty-data baseline until channel analytics are connected.
- Campaign content and execution packages require human review.

## Responsible use

Review generated content before publication. Verify claims, protect customer data, respect consent and opt-out requirements, follow platform policies, and comply with applicable advertising and privacy laws.
