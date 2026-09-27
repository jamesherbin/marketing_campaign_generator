# Local development and environment reference

This guide describes the current FastAPI + Next.js application and its operator
commands. Examples use placeholders, not working credentials. Replace values such
as `campaign-demo`, `CHANGE_ME`, and Firebase identifiers with your own settings.
Do not overwrite an existing environment file when following these instructions.

## 1. Prerequisites

- Python 3.11+, uv, Node.js 20+, and Bun 1.3+.
- PostgreSQL 16 with a persistent database for development campaigns.
- A Firebase project with a registered web app and Google sign-in enabled. Allow
  your local hostname for authentication in that project's configuration.
- Google Application Default Credentials (ADC) usable by the backend and frontend
  servers for Firebase Admin. Operators also need permission to look up users.
- An existing Firebase user, a workspace, and an explicitly assigned membership.

Deterministic runners do not call models or need a Gemini API key, but the running
application still requires PostgreSQL and Firebase authentication. Ordinary unit
and browser fixture tests need no live Firebase credentials.

## Docker Compose quick start

The supported first-run stack is PostgreSQL, the API, and the frontend in
`compose.local.yaml`. It uses the persistent local database on port 5433; the
separate integration-test database on port 55432 is disposable and must not be
used for campaigns you want to keep. Run these commands from the repository root.

Create the ignored root `.env` once. Generate three distinct URL-safe passwords
(hex avoids URL-encoding issues), set the app UID to the output of `id -u`, and
set the ADC path to the absolute path of your local credentials file:

```sh
[ -f .env ] || cp .env.example .env
openssl rand -hex 24
id -u
```

Edit `.env` and replace the three `LOCAL_*_PASSWORD` examples with separate
generated values, `LOCAL_APP_UID` with the `id -u` output, and
`GOOGLE_APPLICATION_CREDENTIALS_HOST` with the full path to
`~/.config/gcloud/application_default_credentials.json` (expand `~` yourself).
The example targets Firebase project `marketing-generator-51cc0`; its public web
configuration must remain matched to `GOOGLE_CLOUD_PROJECT`. These web values are
not credentials. Keep `.env` private and do not add credential files to the repo.

If local ADC does not exist yet, create it with:

```sh
gcloud auth application-default login
```

In the Firebase console for `marketing-generator-51cc0`, ensure Google is enabled
as a sign-in provider and `localhost` is an authorized domain. The developer must
also have an existing Firebase user in this project. Compose mounts ADC
read-only at `/run/secrets/google-adc.json` in both application containers and
runs them as your local UID; do not loosen the host file's permissions. The
Firebase Admin SDK uses this ADC, while browser sign-in uses the public web-app
settings. Both must target the same project.

Start PostgreSQL, initialize restricted database roles, and explicitly apply the
ordered migrations and grants before bringing up the API:

```sh
docker compose -f compose.local.yaml up -d --wait postgres
docker compose -f compose.local.yaml run --rm migrate
docker compose -f compose.local.yaml up -d --build --wait api frontend
docker compose -f compose.local.yaml ps
```

Open the frontend at <http://localhost:3000>, API health at
<http://localhost:8080/health>, and API docs at <http://localhost:8080/docs>.
The API health endpoint reports app startup/runner status; its successful
container health check follows startup schema validation but does not continually
probe PostgreSQL. The frontend health check requests the public `/login` page;
the authenticated frontend `/api/health` route is not an unauthenticated probe.

Provision workspace access once the API is ready and you know the Firebase UID
(not email). The workspace creator is not automatically granted membership, so
run both operator commands from `00_backend/` in a host terminal with backend
dependencies installed. Source the root Compose settings, then explicitly set
the operator database URL; the CLI intentionally does not read Compose `.env`:

```sh
cd 00_backend
uv sync --locked
set -a
source ../.env
set +a
export OPERATOR_DATABASE_MODE=local
export OPERATOR_DATABASE_URL="postgresql://campaign_operator:${LOCAL_CAMPAIGN_OPERATOR_PASSWORD}@127.0.0.1:5433/campaigns"
.venv/bin/python -m campaign.manage workspace-create \
  --name 'Local campaign team' --slug local-campaign-team --creator-uid YOUR_FIREBASE_UID
# Copy workspace_id from the JSON result, then assign your own explicit role:
.venv/bin/python -m campaign.manage member-set \
  --workspace-id WORKSPACE_UUID --uid YOUR_FIREBASE_UID --role approver
```

Sign in at <http://localhost:3000> using the same Firebase account. `approver`
includes viewer, editor, and runner capabilities. The full role behavior is
described under [workspace provisioning](#6-provision-workspace-membership).

Useful lifecycle commands:

```sh
docker compose -f compose.local.yaml logs -f postgres api frontend
docker compose -f compose.local.yaml stop                 # stop, preserve data
docker compose -f compose.local.yaml start                # restart stopped services
docker compose -f compose.local.yaml down                 # remove containers/network; keep DB volume
docker compose -f compose.local.yaml up -d --wait postgres
docker compose -f compose.local.yaml run --rm migrate     # safe to rerun after schema v4
docker compose -f compose.local.yaml up -d --wait api frontend
```

To permanently erase local campaigns and start with an empty database, first
confirm the stack name and then remove this Compose project's volume. This reset
is destructive and cannot be undone; it does not target the separate test
database:

```sh
docker compose -f compose.local.yaml down
docker volume ls --filter name=marketing-campaign-local_campaign-postgres-data
docker volume rm marketing-campaign-local_campaign-postgres-data
```

After a reset, repeat the PostgreSQL, migration, and app startup sequence above.
For service-specific failures, inspect `docker compose -f compose.local.yaml logs <service>`
and confirm root `.env` values. PostgreSQL initialization scripts run
only for a new volume; changing a password in `.env` does not change a role's
password in an existing database volume. Use the explicit volume reset to make
bootstrap changes take effect, or alter the database role deliberately.

Common Compose failures:

| Symptom | Check |
| --- | --- |
| Compose says a variable is unset or still uses an example | Complete root `.env`; replace all password/path placeholders. Compose reads this file automatically from the repo root. |
| ADC bind mount fails or Admin SDK reports credential errors | Confirm `GOOGLE_APPLICATION_CREDENTIALS_HOST` is an existing absolute file path, rerun ADC login if needed, and ensure `LOCAL_APP_UID` equals `id -u`. Keep the file owner-readable; mount is read-only. |
| API exits with database startup/schema error | Check PostgreSQL health and logs, then run the explicit `migrate` service before starting API/frontend. The API does not apply migrations. |
| Frontend is healthy but login fails | Check Firebase Google provider, `localhost` authorized domain, matching project IDs, ADC access, and that the user exists in the project. |
| Session endpoint returns 200 but `/api/auth/me` returns 401 over local HTTP | Rebuild/restart the frontend after config or image changes, use the exact origin in `APP_ORIGIN`, and check that local HTTP cookies are not marked `Secure`. Cookie security follows the configured origin protocol. |
| Google sign-in reuses the previous account | Sign out of the app and choose the intended account from Google's account chooser; the app requests the chooser on each sign-in. |
| Login succeeds but dashboard has no workspace access | Run `workspace-create` and `member-set` for the exact Firebase UID; login alone does not create database membership. |
| A port is already allocated | Stop the conflicting local service or update the published port in Compose and the matching browser/API settings. |

Contributors preferring native Python/Bun servers can use the environment and
commands in the sections below; the Compose stack and native workflow share the
same Firebase and database requirements.

## 2. Where and how to define variables

| Consumer | Where to define values | Loading behavior |
| --- | --- | --- |
| Backend application settings | `00_backend/.env` or the backend terminal's exported environment | Pydantic reads `.env` relative to the working directory; exported values override file values. Start from `00_backend/`. |
| Frontend | `00_frontend/.env.local` or the frontend terminal's exported environment | Next.js loads project environment files. Exported values take precedence. |
| Operator database settings | Export `OPERATOR_DATABASE_*` in the operator terminal | CLI does **not** load these from `.env` and never falls back to `DATABASE_*`. |
| Google credentials and model SDK settings | Export in each terminal that starts a relevant process | A Pydantic `.env` read does not export values into the process environment for other SDKs. |
| Tests, migrations, export session | Export in the terminal executing the command, or prefix that one command | Tools do not automatically load these values from the application `.env`. |

Create files only if they do not already exist, from the repository root:

```sh
[ -f 00_backend/.env ] || cp 00_backend/.env.example 00_backend/.env
[ -f 00_frontend/.env.local ] || cp 00_frontend/.env.example 00_frontend/.env.local
```

Use `KEY=value` lines in environment files, without `export`. Quote values containing
spaces or `#`. Use full absolute paths for credential files; do not rely on `~`
expansion inside a dotenv file. Real `.env` files are ignored by Git.

In a zsh/bash terminal, set variables before launching the process:

```sh
export GOOGLE_CLOUD_PROJECT=campaign-demo
export API_URL=http://localhost:8080
```

Or apply a value to one command only:

```sh
CAMPAIGN_RUNNER_MODE=deterministic .venv/bin/python main.py
```

An export affects that terminal and its child processes, not another open terminal.
To remove a value, use `unset VARIABLE_NAME` and remove/comment its file entry.
For mutually exclusive database settings, remove the unused settings rather than
setting them to empty strings. Restart servers after configuration changes. Rebuild
production frontend output after changing `NEXT_PUBLIC_*` values because those
values are embedded in the browser bundle.

## 3. Configure credentials and prepare PostgreSQL

For local user ADC, run:

```sh
gcloud auth application-default login
```

The signed-in Google identity must have the necessary project permissions. A
successful login alone does not grant Firebase or database permissions.

Alternatively, if you already have an authorized service-account credential file,
keep it outside the repository and export its location in each relevant terminal:

```sh
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/private/path/campaign-dev-service-account.json
export GOOGLE_CLOUD_PROJECT=campaign-demo
```

Choose one ADC approach. Leave `GOOGLE_APPLICATION_CREDENTIALS` unset when using
local user ADC so a stale key-file path does not override it. The Firebase browser
API key is not an ADC credential or a Gemini API key.

Create a dedicated PostgreSQL database and three distinct identities: a migration
owner, a restricted runtime login, and a restricted operator login. Apply migrations
`001`–`004` in order and `grants.sql` as the migration owner. See
[database setup](database/README.md#apply-migrations) for exact SQL commands and
role restrictions. Application startup checks the schema; it does not apply it.

Example connection values, once those database/logins exist:

```sh
# Migration terminal only; replace each password and URL-encode reserved characters.
export MIGRATION_DATABASE_URL='postgresql://campaign_migrator:CHANGE_ME@127.0.0.1:5432/campaigns'
```

The API uses `campaign_runtime`, and management commands use `campaign_operator`.
Do not use the migration owner or test superuser as the API login. The Docker
service in `database/compose.test.yaml` is disposable and must not store campaigns
you want to keep.

## 4. Configure and start the backend

Edit `00_backend/.env` with these minimum explicit values:

```dotenv
CAMPAIGN_RUNNER_MODE=deterministic
DATABASE_MODE=local
DATABASE_URL=postgresql://campaign_runtime:CHANGE_ME@127.0.0.1:5432/campaigns
GOOGLE_CLOUD_PROJECT=campaign-demo
PORT=8080
LOG_LEVEL=info
```

From a terminal with ADC configured:

```sh
cd 00_backend
uv sync --locked
.venv/bin/uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080/health`; API schemas are at
`http://localhost:8080/docs`. `/health` reports startup/runner status, not a live
database connectivity check. For the `PORT` and `LOG_LEVEL` application settings
to control server startup directly, use `.venv/bin/python main.py`. An explicit
Uvicorn CLI invocation uses its own `--port` and `--log-level` options instead.

### Backend variable reference

All settings below can be defined in `00_backend/.env` or exported, except the
credential path, which should be exported for SDK use. Export the ADK/model-related
settings as shown later when using live models.

| Variable | Required/default | Purpose and example |
| --- | --- | --- |
| `CAMPAIGN_RUNNER_MODE` | Optional; `deterministic` | `deterministic` for placeholder outputs; `adk` for live agents. |
| `PORT` | Optional; `8080` | Port used by `python main.py`; integer 1–65535. Example: `8080`. |
| `LOG_LEVEL` | Optional; `info` | Uvicorn level used by `python main.py`. Example: `debug`. |
| `DATABASE_MODE` | Optional; `local` | `local` uses a PostgreSQL URL; `cloud_sql` uses the private Cloud SQL connector with IAM. |
| `DATABASE_URL` | Required in `local`; must be unset in `cloud_sql` | Runtime connection, e.g. `postgresql://campaign_runtime:CHANGE_ME@127.0.0.1:5432/campaigns`. Treat as a secret. |
| `DATABASE_INSTANCE` | Required in `cloud_sql`; unset in `local` | Cloud SQL connection name: `campaign-demo:us-central1:campaign-postgres`. |
| `DATABASE_NAME` | Required in `cloud_sql`; unset in `local` | Database name, e.g. `campaigns`. Local mode gets it from the URL. |
| `DATABASE_USER` | Required in `cloud_sql`; unset in `local` | Provisioned IAM database username, e.g. `campaign-api@campaign-demo.iam`. |
| `DATABASE_POOL_MIN_SIZE` | Optional; `1` | Minimum connections, integer 1–100. Example: `1`. |
| `DATABASE_POOL_MAX_SIZE` | Optional; `10` | Maximum connections, integer 1–100 and at least the minimum. Example: `10`. |
| `DATABASE_CONNECT_TIMEOUT` | Optional; `10` seconds | Connection timeout, greater than 0 and at most 120. Example: `10`. |
| `DATABASE_COMMAND_TIMEOUT` | Optional; `30` seconds | Database command timeout, greater than 0 and at most 300. Example: `30`. |
| `DATABASE_SHUTDOWN_TIMEOUT` | Optional; `10` seconds | Graceful pool close timeout, greater than 0 and at most 120. Example: `10`. |
| `GOOGLE_CLOUD_PROJECT` | Set explicitly for predictable Firebase project selection | Firebase Admin project; also used by Vertex AI. Example: `campaign-demo`. Backend may otherwise discover the project through ADC. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional; unset for user ADC | Exported absolute path to an authorized Google credential file. Example: `/absolute/private/path/campaign-dev-service-account.json`. Never the JSON content itself. |
| `GEMINI_API_KEY` | Only for Gemini API authentication in ADK mode | Secret model key; example placeholder: `REPLACE_WITH_GEMINI_KEY`. Leave unset in deterministic/Vertex mode. |
| `GOOGLE_API_KEY` | Alternative to `GEMINI_API_KEY` | Secret Gemini API key; define one key variable, not both. Example placeholder: `REPLACE_WITH_GEMINI_KEY`. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Optional; `false` | Set `true` to use Vertex AI with ADC instead of Gemini API key authentication. |
| `GOOGLE_CLOUD_LOCATION` | Optional application default; `us-central1` | Vertex AI region. Export explicitly for the model SDK, e.g. `us-central1`. |

Cloud SQL mode is optional for local development. ADC alone does not supply
network access to a private instance; the local machine must have the required
private connectivity and the IAM database user/grants must already exist.

## 5. Configure and start the frontend

Edit `00_frontend/.env.local`:

```dotenv
API_URL=http://localhost:8080
APP_ORIGIN=http://localhost:3000
GOOGLE_CLOUD_PROJECT=campaign-demo
NEXT_PUBLIC_FIREBASE_API_KEY=REPLACE_WITH_FIREBASE_WEB_API_KEY
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=campaign-demo.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=campaign-demo
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789012:web:abcdef0123456789
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789012
```

Get the five public Firebase values from your registered Firebase web app's SDK
configuration: `apiKey`, `authDomain`, `projectId`, `appId`, and `messagingSenderId`.
The examples above do not identify a working app. Match the backend's Firebase
project. Review the copied example file rather than assuming its existing project
values belong to your environment.

These five `NEXT_PUBLIC_FIREBASE_*` values are compiled into the frontend image
at build time. They are public web-app configuration, not service-account
credentials or private API keys. The frontend Dockerfile requires all five build
arguments.

In a second terminal, from the repository root, with ADC configured:

```sh
cd 00_frontend
bun install --frozen-lockfile
bun run dev
```

Open `http://localhost:3000`. Browser requests use same-origin `/api` routes; the
Next.js server forwards campaign requests to `API_URL` with the verified session
and selected workspace. Do not expose server credentials as `NEXT_PUBLIC_*`.

### Frontend variable reference

| Variable | Required/default | Purpose and example |
| --- | --- | --- |
| `API_URL` | Recommended explicitly; fallback described below | Server-only FastAPI base URL, without `/api/v1`. Example: `http://localhost:8080`. |
| `APP_ORIGIN` | Recommended explicitly; request origin is also trusted | Additional trusted origin for session creation/logout checks. Example: `http://localhost:3000`; use the exact scheme/host/port you visit. |
| `GOOGLE_CLOUD_PROJECT` | Recommended; falls back to public Firebase project ID | Firebase Admin project, e.g. `campaign-demo`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional; unset for user ADC | Google SDK credential path; export it in this terminal if using a file. Same meaning as the backend variable. |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Required, no default | Firebase web app `apiKey`; public Firebase configuration, e.g. `REPLACE_WITH_FIREBASE_WEB_API_KEY`. Not the model API key. |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Required, no default | Firebase web app `authDomain`, e.g. `campaign-demo.firebaseapp.com`. |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Required, no default | Firebase web app `projectId`, e.g. `campaign-demo`. |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Required, no default | Firebase web app `appId`, e.g. `1:123456789012:web:abcdef0123456789`. |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Required, no default | Firebase web app `messagingSenderId`, e.g. `123456789012`. Required by this app's configuration check even if you do not use messaging. |
| `NEXT_PUBLIC_API_URL` | Legacy fallback; leave unset for normal local use | Proxies use `API_URL`, then this value, then `http://localhost:8080`. `next.config.js` also exposes a default of localhost for this public setting. Example if needed: `http://localhost:8080`. Never put secrets in it. |
| `NEXT_PUBLIC_FRONTEND_URL` | Not required; currently unused by application code | Present in example/build configuration but does not currently set metadata or security behavior. Example: `http://localhost:3000`. Set `APP_ORIGIN` for origin checks. |
| `NODE_ENV` | Managed by Next.js | `development` for `bun run dev`, `production` for production builds/server. It does not control session-cookie security; cookie `Secure` follows the configured frontend origin protocol. Do not set manually for ordinary development. |
| `PORT` | Next CLI normally defaults to `3000` | For a different dev port, use `bun run dev --port 3001` and update `APP_ORIGIN`. Do not depend on setting it in `.env.local`; set a CLI option or export before launch. |
| `HOSTNAME` | Standalone server/container setting | Standalone bind address. Production Dockerfile sets `0.0.0.0`; browser test launcher sets `127.0.0.1`. No local dev override needed. |
| `NEXT_TELEMETRY_DISABLED` | Optional; container sets `1` | Set/export `1` to disable Next.js telemetry. Not needed for application functionality. |

The same variable name in two terminal processes is independent: backend
`PORT=8080` does not set the frontend port. Public Firebase values must be available
at build time for production bundles as well as during local development.

## 6. Provision workspace membership

In a separate operator terminal, configure ADC and export the connection values.
From `00_backend/`:

```sh
export GOOGLE_CLOUD_PROJECT=campaign-demo
export OPERATOR_DATABASE_MODE=local
export OPERATOR_DATABASE_URL='postgresql://campaign_operator:CHANGE_ME@127.0.0.1:5432/campaigns'

.venv/bin/python -m campaign.manage workspace-create \
  --name 'Local campaign team' --slug local-campaign-team --creator-uid YOUR_FIREBASE_UID

# Substitute the workspace_id printed by workspace-create.
.venv/bin/python -m campaign.manage member-set \
  --workspace-id RETURNED_WORKSPACE_UUID --uid YOUR_FIREBASE_UID --role approver
```

The Firebase account must already exist. Copy its UID, not its email address.
Workspace creation does not grant membership automatically. Roles are cumulative:
`viewer` reads, `editor` also creates, `runner` also runs, and `approver` also approves
or rejects. These are database memberships, not environment variables or token
claims. Sign in through the frontend afterward; a sole workspace is auto-selected.

### Operator, migration, and test variables

Operator database fields have the same defaults, units, and validation as runtime
database fields, but must be exported explicitly. Define only the connection mode
you use; optional tuning may remain unset.

| Variable | Required/default | Purpose and example |
| --- | --- | --- |
| `OPERATOR_DATABASE_MODE` | Optional; `local` | `local` or `cloud_sql`. |
| `OPERATOR_DATABASE_URL` | Required for local operator commands | `postgresql://campaign_operator:CHANGE_ME@127.0.0.1:5432/campaigns`; unset in Cloud SQL mode. |
| `OPERATOR_DATABASE_INSTANCE` | Required in Cloud SQL mode only | `campaign-demo:us-central1:campaign-postgres`; unset in local mode. |
| `OPERATOR_DATABASE_NAME` | Required in Cloud SQL mode only | `campaigns`; unset in local mode. |
| `OPERATOR_DATABASE_USER` | Required in Cloud SQL mode only | `campaign-operator@campaign-demo.iam`; unset in local mode. |
| `OPERATOR_DATABASE_POOL_MIN_SIZE` | Optional; `1` | Minimum connections, 1–100. |
| `OPERATOR_DATABASE_POOL_MAX_SIZE` | Optional; `10` | Maximum connections, 1–100 and at least the minimum. |
| `OPERATOR_DATABASE_CONNECT_TIMEOUT` | Optional; `10` seconds | Connection timeout, greater than 0 and at most 120. |
| `OPERATOR_DATABASE_COMMAND_TIMEOUT` | Optional; `30` seconds | Command timeout, greater than 0 and at most 300. |
| `OPERATOR_DATABASE_SHUTDOWN_TIMEOUT` | Optional; `10` seconds | Pool close timeout, greater than 0 and at most 120. |
| `MIGRATION_DATABASE_URL` | Needed for documented `psql` migration commands | Shell variable used by the runbook, not an application setting. Example: `postgresql://campaign_migrator:CHANGE_ME@127.0.0.1:5432/campaigns`. |
| `CAMPAIGN_EXPORT_SESSION` | Only when exporting without `--session-file` | Secret Firebase session cookie accepted by the old API. Prefer a protected file and `--session-file /private/path/session-cookie`; do not paste a real session into this guide or shell history. |
| `CAMPAIGN_IMPORT_ID` | Used by runbook import/retry commands | Shell variable holding a stable UUID, e.g. `12345678-1234-4234-8234-123456789abc`. Generate once with `export CAMPAIGN_IMPORT_ID="$(.venv/bin/python -c 'import uuid; print(uuid.uuid4())')"`, then save/reuse it for the same import. The CLI receives it through `--import-id`. |
| `TEST_DATABASE_URL` | Required for PostgreSQL integration tests only | `postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test`. These are committed disposable test credentials, not application credentials. |

Use the [operations runbook](database/OPERATIONS.md) for export, dry-run, import,
verification, and recovery. Imports create a **new** workspace; do not pre-create
that migration workspace. Existing campaign state must be exported before the old
in-memory backend is stopped. The ordinary local-start sequence above does not
perform a migration of old campaign data.

## 7. Optional live model configuration

In the backend terminal, select one authentication mode and export its SDK settings.
The typed backend settings read `.env`, but the runner factory does not copy those
values into the Google model SDK's environment. Exporting removes that ambiguity.

Gemini API mode:

```sh
export CAMPAIGN_RUNNER_MODE=adk
export GOOGLE_GENAI_USE_VERTEXAI=false
export GEMINI_API_KEY='REPLACE_WITH_GEMINI_KEY'
unset GOOGLE_API_KEY
.venv/bin/uvicorn main:app --reload --port 8080
```

Vertex AI mode, with authorized ADC:

```sh
export CAMPAIGN_RUNNER_MODE=adk
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=campaign-demo
export GOOGLE_CLOUD_LOCATION=us-central1
unset GEMINI_API_KEY GOOGLE_API_KEY
.venv/bin/uvicorn main:app --reload --port 8080
```

Keep the Firebase and Vertex project choice consistent with the shared
`GOOGLE_CLOUD_PROJECT` setting. If unused keys remain in `.env`, remove/comment them
there as well. Live model calls require the selected project's access and may incur
charges; deterministic mode avoids those calls.

## 8. Validation and troubleshooting

From `00_backend/`, run unit tests:

```sh
.venv/bin/python -m pytest -m 'not integration'
```

For PostgreSQL tests, start the isolated service from the repository root:

```sh
docker compose -f database/compose.test.yaml up -d --wait
```

Then from `00_backend/`:

```sh
TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test \
  .venv/bin/python -m pytest -m integration
```

From `00_frontend/`, run sequentially:

```sh
bun run test
bun run lint
bun run build
bunx playwright install chromium --only-shell
bun run test:browser
```

Browser tests start their own loopback server on port 3100 with synthetic sessions
and API fixtures. Leave that port free. They do not validate live Google sign-in.

| Symptom | Check |
| --- | --- |
| Backend startup rejects configuration | Run from `00_backend/`; set the correct `DATABASE_MODE` and mutually exclusive connection fields. |
| Database schema is not ready | Apply migrations 001–004 and grants using the migration identity. |
| Authentication fails | Match frontend/backend Firebase projects, configure ADC in the server process, and verify the Firebase account/provider/hostname setup. |
| Dashboard says workspace access needed | Use `member-set` for the exact Firebase UID and correct workspace; login alone does not provision membership. |
| Operator configuration fails despite a working API | Export `OPERATOR_DATABASE_*`; the CLI intentionally ignores runtime database values and `.env` for operator settings. |
| Local frontend calls a deployed backend | Check `API_URL` in `.env.local` and exported shell variables; an exported value overrides the file. Restart Next.js. |
| Session/logout returns invalid origin | Use one hostname consistently (`localhost` versus `127.0.0.1`) and align `APP_ORIGIN` with the browser URL. |
| Changed frontend public configuration has no effect | Restart dev mode or rebuild production; public values are embedded at build time. |

## Scope and source references

This inventory covers the application's own settings, operator/migration commands,
and local test/development settings. It is not an exhaustive list of every variable
accepted internally by Python, Node, Google SDKs, Docker, or shell tools.
`PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `PIP_DISABLE_PIP_VERSION_CHECK`, and
`PIP_NO_CACHE_DIR` are set to `1` by the backend Dockerfile for container behavior;
you do not need to define them for local application startup.

The older root `cloudbuild.yaml` mentions `FIREBASE_STORAGE_BUCKET`, `API_BASE_URL`,
and `MAP_BASE_URL`; current campaign application code does not read them. Do not
use them in place of `API_URL` or `APP_ORIGIN`. Cloud Build substitutions such as
`_REGION`, `PROJECT_ID`, and `BUILD_ID`, and Terraform input variables, belong to
deployment tooling and are not local application environment requirements.

Checked against [backend settings](00_backend/campaign/config.py),
[Firebase verification](00_backend/campaign/auth.py),
[operator CLI](00_backend/campaign/manage.py),
[frontend client settings](00_frontend/lib/firebase-client.ts),
[frontend Admin settings](00_frontend/lib/firebase-admin.ts), and
[frontend proxy](00_frontend/lib/backend-proxy.ts).
## Build local Docker images

Run both build commands from the repository root. The backend Docker build context
must be the repository root because the image copies `agents/` and `00_backend/`.
The frontend context is `00_frontend/`.

```sh
docker build \
  -f 00_backend/Dockerfile \
  -t marketing-campaign-api:local \
  .

docker build \
  -f 00_frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8080 \
  --build-arg NEXT_PUBLIC_FRONTEND_URL=http://localhost:3000 \
  --build-arg NEXT_PUBLIC_FIREBASE_API_KEY=REPLACE_WITH_FIREBASE_WEB_API_KEY \
  --build-arg NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=campaign-demo.firebaseapp.com \
  --build-arg NEXT_PUBLIC_FIREBASE_PROJECT_ID=campaign-demo \
  --build-arg NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789012:web:abcdef0123456789 \
  --build-arg NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789012 \
  -t marketing-campaign-frontend:local \
  00_frontend
```

Replace the Firebase examples with values from your Firebase web app. Build args
are appropriate here because these values are public and go into the browser
bundle. Never pass database URLs, service account keys, session cookies, or model
API keys as image build arguments. Configure backend database/Firebase Admin ADC
and frontend server `API_URL`, `APP_ORIGIN`, and Google ADC when starting the
containers; those are runtime settings, not build arguments. In particular,
`API_URL` for the frontend is the backend URL reachable **from the frontend
container**, so `localhost` only works if the backend shares that network namespace.
