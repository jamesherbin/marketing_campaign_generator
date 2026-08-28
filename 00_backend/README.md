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
