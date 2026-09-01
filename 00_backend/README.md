# Campaign Orchestrator API

The backend owns the canonical `CampaignState` and advances it through planning,
development, execution, and monitoring. State is currently stored in memory, so
it is intended for local development until a durable repository is added.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080/docs` for the generated OpenAPI interface.

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

Pass phase runners through `CampaignOrchestrator(..., runners={...})`. All four
phases must be present in the mapping. Live calls require Gemini API-key or
Vertex AI authentication.

Set `CAMPAIGN_RUNNER_MODE=adk` to make the API invoke the four ADK agents. The
default is `deterministic`, which is safe for local development and tests and
does not make model calls.

```bash
export CAMPAIGN_RUNNER_MODE=adk
export GEMINI_API_KEY="..."  # or configure Vertex AI credentials
uvicorn main:app --port 8080
```

`GET /health` reports the active runner mode.

## Container and Cloud Run

Build and run the production container locally:

```bash
docker build -f 00_backend/Dockerfile -t campaign-api:dev .
docker run --rm -p 8080:8080 \
  -e GOOGLE_CLOUD_PROJECT=marketing-generator-51cc0 \
  campaign-api:dev
```

Run the build command from the repository root. The root build context includes
the `agents` package required by `CAMPAIGN_RUNNER_MODE=adk`; `.dockerignore`
excludes frontend dependencies, local credentials, tests, caches, and build output.

The image runs as an unprivileged user, listens on Cloud Run's `PORT`, and does
not contain credentials. For authenticated campaign requests, use Application
Default Credentials locally or attach a dedicated service account to Cloud Run.
Do not bake a Firebase service-account key or Gemini API key into the image.

Build and deploy with Google Cloud Build and Cloud Run:

```bash
gcloud builds submit \
  --config 00_backend/cloudbuild.yaml \
  --project marketing-generator-51cc0 \
  .

gcloud run deploy campaign-api \
  --image us-east4-docker.pkg.dev/marketing-generator-51cc0/marketing-campaign-generator/campaign-api:BUILD_ID \
  --region us-east4 \
  --service-account campaign-api@marketing-generator-51cc0.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_CLOUD_PROJECT=marketing-generator-51cc0,CAMPAIGN_RUNNER_MODE=deterministic \
  --allow-unauthenticated
```

`--allow-unauthenticated` permits the Firebase App Hosting server to reach Cloud
Run; FastAPI still requires and verifies a Firebase session on all campaign
routes. For stronger network-level isolation, make Cloud Run private after the
frontend proxy is extended to attach a Google-signed Cloud Run identity token.

The current repository is in-memory. Keep the container at one process for local
testing only; Cloud Run instances do not share memory and lose campaign state on
restart. Connect the PostgreSQL repository before using multiple instances or
serving production campaign data.

## Environment configuration

Configuration is loaded and validated by `campaign.config.Settings`. Values come
from process environment variables, with an optional local `.env` file. Copy
`.env.example` to `.env` for local development; never commit real credentials.
API keys are represented as Pydantic secret values so they are redacted from
settings logs and representations.
