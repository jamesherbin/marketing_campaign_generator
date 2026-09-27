# 002: Repeatable local development stack

Status: Implemented

## Problem and outcome

A developer setting up the application for the first time needs more than Docker
image build and run commands. The current instructions require a persistent
PostgreSQL database and provisioned Firebase identity/workspace, while the
available PostgreSQL Compose service is temporary test infrastructure on port
55432. Pointing the API at that service does not provide the schema, restricted
application roles, or durable storage needed for running the application.

Provide one documented, repeatable local setup that runs the application against
its own persistent PostgreSQL database, keeps automated-test infrastructure
isolated, and guides a developer through Firebase authentication and workspace
provisioning without placing credentials in images or source control.

## Scope

In scope:

- A supported Docker Compose workflow for local PostgreSQL, backend API, and
  frontend, using the existing production container images where appropriate.
- Persistent local campaign data, database roles, migrations, and grants.
- Environment configuration, Firebase Admin credentials, and public Firebase web
  configuration required to build and run the app locally.
- Deterministic campaign execution by default, first-run workspace membership
  provisioning, health checks, and documented start/stop/reset steps.
- Clear separation from the disposable PostgreSQL integration-test service.

Out of scope:

- GCP, Cloud Run, Cloud SQL, CI deployment, staging, or production setup.
- Firebase project creation, user invitation, or a Firebase emulator workflow.
- Live model provider setup and external campaign publication.
- Changes to campaign, authorization, or database runtime contracts.
- Migration of existing production campaign data into a developer database.

## Requirements and acceptance scenarios

### 002-R1: First-run local startup

The repository must provide a documented Compose-based path that takes a
developer from a clean checkout and configured local prerequisites to a running
frontend, API, and local PostgreSQL database.

- Given Docker Compose and valid local configuration, when the developer follows
  the documented first-run commands, then the frontend and API start and the API
  connects to the local development database.
- Given missing required Firebase configuration or database configuration, when
  the developer starts or builds the stack, then setup fails with a clear
  actionable error rather than silently using placeholder values.

### 002-R2: Persistent and isolated database state

The local development database must persist across container restarts and remain
separate from the disposable integration-test database.

- Given a campaign stored in the local development database, when the app
  containers are restarted, then the campaign remains available.
- Given the disposable test service on its documented port, when local
  development services start or stop, then the test service's database and
  lifecycle are not reused, reset, or modified by the development stack.
- Given the developer requests a full local reset, when following the documented
  reset command, then only the local development database volume is deleted and
  the command warns that its campaign data will be lost.

### 002-R3: Database initialization and least privilege

The local database setup must support ordered migrations and grants using a
migration/schema-owner identity, while the backend and operator use separate
restricted identities.

- Given a new local database volume, when the documented initialization and
  migration steps complete, then migrations 001–004 and `grants.sql` are applied
  and the API can validate the required schema.
- Given the backend connects to PostgreSQL, when it performs normal campaign
  operations, then it uses the restricted runtime identity rather than the
  migration owner or test superuser.
- Given workspace/member provisioning, when the operator command runs, then it
  uses the separate operator identity.

### 002-R4: Firebase configuration and credential handling

The local setup must distinguish public Firebase browser configuration from
server-side Firebase Admin credentials.

- Given valid Firebase web-app values, when the frontend image is built, then
  those public values are available to the browser bundle and match the Firebase
  project used by the backend.
- Given the repository's current local example configuration, when a developer
  starts the local stack without overriding the Firebase settings, then the
  frontend and backend target `marketing-generator-51cc0` consistently.
- Given Firebase Admin credentials configured for local use, when the frontend
  server or API performs an Admin SDK operation, then it can read the credential
  without embedding it in an image or committing it to the repository.
- Given the documented workflow is run, then Firebase credentials and database
  passwords remain in ignored local configuration or protected files, not in
  tracked files or image layers.
- Given a developer creates a local `.env` variant or stores a standard ADC,
  service-account, credential, or private-key file in the repository, when Git
  evaluates ignore rules, then that file is ignored while `.env.example`
  templates remain eligible for tracking.

### 002-R5: Reproducible application behavior

The default local runner must avoid live model-provider calls while exercising
the same authentication, workspace authorization, API, and database boundaries
as the application.

- Given the local stack is configured for deterministic mode and no model API
  credentials are present, when a member runs a campaign phase, then the local
  deterministic runner returns its defined output without contacting a model
  provider.
- Given a Firebase-authenticated user with a provisioned workspace membership,
  when they sign in through the local frontend, then they can select/access the
  workspace and use permitted campaign operations.
- Given a Firebase-authenticated user without workspace membership, when they
  access the dashboard, then the existing no-membership behavior is shown and no
  campaign data is exposed.

### 002-R6: Lifecycle and troubleshooting documentation

The local setup guide must document prerequisite configuration, start and stop,
logs, health checks, workspace provisioning, persistence, reset, and common
connection or credential failures.

- Given a developer following only the local setup guide, when any required local
  service fails to start, then the guide identifies the relevant logs and
  configuration to inspect.
- Given the developer stops the app stack without requesting a reset, when they
  start it again, then the database volume and its data remain intact.

### 002-R7: Origin-aware Firebase session cookies

Session-cookie security attributes must match the configured frontend origin,
including when the production container image is used for local HTTP development.

- Given the frontend is served from a configured HTTP origin, when Firebase
  session creation succeeds, then the session cookie is set without the `Secure`
  attribute and is accepted on subsequent same-origin requests.
- Given the frontend is served from a configured HTTPS origin, when Firebase
  session creation succeeds, then the session cookie is set with the `Secure`
  attribute.
- Given a session cookie is cleared, when the logout route responds, then it uses
  the same origin-derived `Secure` setting as session creation.

### 002-R8: Selectable Google sign-in account

The local Google sign-in flow must let a developer choose an account even when
the browser already has an active Google session.

- Given the developer has signed out of the application but Google still has an
  active browser session, when they start sign-in again, then Google presents an
  account chooser so they can authenticate as a different Firebase user.
- Given the developer chooses a different Google account, when sign-in completes,
  then the frontend creates the Firebase session for the chosen account.

## Contracts and compatibility

No API routes, Pydantic models, frontend API contracts, or campaign storage schema
are changed by this setup. It uses database migrations 001–004 and the existing
runtime/operator permissions. The local Compose database is a new development
service and must not share a database, volume, credentials, or lifecycle with
`database/compose.test.yaml`.

The frontend currently embeds `NEXT_PUBLIC_FIREBASE_*` and public URL settings at
build time. The local workflow must supply those values during image build. The
backend and frontend server-side Firebase Admin clients require Google
Application Default Credentials readable from inside their containers. No
service-account file or user ADC file may be copied into an image.

## Decisions and assumptions

- Use Compose for PostgreSQL, API, and frontend as the supported first-run path;
  native Python/Bun workflows remain available for contributors who prefer them.
- Use Compose services `postgres`, `api`, and `frontend`; expose host ports 5433
  (PostgreSQL, loopback only), 8080 (API), and 3000 (frontend). Container-to-
  container URLs are `postgres:5432` and `api:8080`.
- Keep Compose settings in root `.env`, provide `.env.example`, and use the
  existing `.env` ignore rule. Never commit local passwords or ADC paths.
- Use a named PostgreSQL volume. Ordinary stop/down preserves local data; an
  explicit reset removes only this development volume.
- Use separate `campaign_migrator`, `campaign_runtime`, and
  `campaign_operator` database logins. Apply migrations and grants explicitly
  before starting the API; API startup only validates the schema.
- Use deterministic campaign runners by default. Firebase authentication and
  Firebase Admin still require a configured Firebase project and credentials.
- Use the currently configured Firebase project `marketing-generator-51cc0` for
  local sign-in; keep its settings overrideable. Its web-app values are public
  configuration and must match the backend project.
- Mount the developer ADC file read-only and configure local app image UIDs/GIDs
  to read it without broadening host file permissions or running as root. Preserve
  Next.js cache write access.
- Keep `database/compose.test.yaml` unchanged and isolated on port 55432.
- A live Firebase sign-in walkthrough is an environment-dependent manual check;
  deterministic tests must not require cloud credentials.
- GCP repeatability is deliberately handled outside this spec. Current Cloud Run
  deployment configuration does not yet supply the full Cloud SQL runtime
  contract.

No user decisions remain open before implementation. The service topology,
Firebase project, persistent test-isolated database, credential strategy, and
migration order are resolved above.

## Evidence

| Requirement | Test or check | Result and date |
| --- | --- | --- |
| 002-R2 | Fresh isolated Compose project; seeded one campaign, restarted API/frontend, queried through API runtime connection, checked test database, then removed isolated project with `down --volumes` | Campaign count remained 1 across app restart; runtime connection used `campaign_runtime`; separate disposable test PostgreSQL remained healthy; only the T05 project volume was removed (2026-09-26) |
| 002-R3 | Isolated Compose migration run twice; query schema version, role flags, and representative grants | Migrations 001–004 and grants passed; rerun no-op at version 4; all app roles non-superuser/no-createdb/no-createrole; runtime campaign SELECT true/user UPDATE false; operator membership INSERT true (2026-09-26) |
| 002-R1 | First-run Compose sequence on a fresh, isolated project using a temporary environment file; missing-value validation | PostgreSQL initialized, migrations and grants applied, both images built, all three service health checks passed. Blank runtime password and Firebase App ID each failed Compose validation with a message naming the missing setting (2026-09-26) |
| 002-R4 | Inspect Compose build configuration, runtime mounts, images, Git ignore rules and index; read-only Firebase Admin user lookups | Both apps target `marketing-generator-51cc0`; ADC was readable in both app containers, mounts reported `RW=false`, and neither image contained the ADC file/path. Admin SDK verified both supplied Firebase UIDs as present and enabled. `git check-ignore` confirms local `.env` variants and standard ADC/service-account/private-key filenames are ignored while `.env.example` remains eligible for tracking; tracked-file audit found no credential artifacts (2026-09-26) |
| 002-R5 | Backend unit, PostgreSQL integration, and frontend test suites; provision live Firebase identities | 63 non-integration backend tests, all 42 PostgreSQL integration tests, and 42 frontend tests pass (2026-09-26). One live Firebase UID has active approver membership in the local T07 workspace; the second verified UID has zero active memberships. The user confirmed live sign-in, campaign operations, and the no-workspace/data-denial behavior for the unprovisioned account (2026-09-26). |
| 002-R6 | Follow documented first-run, health, restart, and reset commands against isolated Compose project | Services became healthy, API/frontend restart preserved the campaign, and `down --volumes` removed only the isolated T05 database volume. The separate test PostgreSQL remained healthy. Logs and troubleshooting commands are documented in `LOCAL_DEVELOPMENT.md` (2026-09-26) |
| 002-R7 | Frontend auth-cookie route tests and live HTTP sign-in/logout | Four route-level cases inspect serialized session and logout `Set-Cookie` headers: HTTPS sets `Secure`, HTTP omits it, and logout uses `Max-Age=0` in both cases. The helper-origin tests also pass; frontend suite: 42 tests passed, lint and production build passed. User confirmed local HTTP sign-in and logout work (2026-09-26) |
| 002-R8 | Google provider account-selection configuration and live account-switch check | Unit test confirms each new Google provider requests `prompt=select_account`; frontend image rebuilt and container is healthy. User confirmed live account switching (2026-09-26) |
