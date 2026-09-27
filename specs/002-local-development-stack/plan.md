# 002: Local development stack implementation plan

Spec: [spec.md](spec.md)

## Approach

Provide `compose.local.yaml`, separate from the existing test Compose file. Run
PostgreSQL 16 with a named volume and explicit health check; run the backend and
frontend on a private Compose network and publish only developer-facing ports
(PostgreSQL at `127.0.0.1:5433`, API at 8080, frontend at 3000). Containers connect
to PostgreSQL at `postgres:5432` and the backend at `api:8080`. Keep local
configuration in an ignored root `.env` with a tracked `.env.example`; do not
reuse the existing tmpfs-backed test database.

Initialize the distinct `campaign_migrator`, `campaign_runtime`, and
`campaign_operator` database logins. Apply migrations 001–004 and grants through
an explicit ordered migration command before starting the API. The API uses only
the runtime identity and validates, but does not apply, the schema. Operator
commands use only the operator identity.

Supply public Firebase web values as frontend build arguments, targeting the
currently configured project `marketing-generator-51cc0` by default. Mount the
developer's ADC file read-only into the API and frontend server. Configure local
app images to run with compatible host UID/GID values so they can read a
mode-0600 ADC file while remaining non-root. Preserve the frontend's cache write
access. Do not copy credentials into either image or weaken host file
permissions.

Use deterministic campaign execution by default. Document Firebase project
authorized origins, user sign-in, and operator CLI steps to create a workspace
and assign the developer an explicit role. Update `LOCAL_DEVELOPMENT.md` as the
operational guide and link the Compose entry point from the repository README.

## Affected components

| Component/path | Change | Requirement IDs |
| --- | --- | --- |
| `compose.local.yaml` | Persistent PostgreSQL, explicit migration service, API/frontend networking, health checks, Firebase config and read-only ADC mounts | 002-R1, 002-R2, 002-R4 |
| Root `.env.example` | Safe local database password placeholders, local UID, ADC path, and current Firebase web config | 002-R1, 002-R4 |
| `00_frontend/Dockerfile` | Build-time local UID ownership for writable Next.js cache while preserving non-root production default | 002-R4 |
| `database/local/init/010-app-roles.sql` | Create restricted database logins and disable bootstrap login | 002-R3 |
| `database/local/migrate.sh` | Apply ordered migrations and grants; reject partial state and safely rerun at version 4 | 002-R3 |
| `database/README.md` | Document local PostgreSQL bring-up and explicit migration command | 002-R2, 002-R3 |
| `LOCAL_DEVELOPMENT.md` | First-run, credentials, workspace provisioning, lifecycle, and troubleshooting runbook | 002-R1–R6 |
| `README.md` | Link to the Compose first-run path | 002-R1, 002-R6 |
| `specs/README.md` | Index spec 002 | 002-R1–R6 |

## Decisions and dependencies

- Use Compose services `postgres`, `api`, and `frontend`; publish host ports 5433
  (loopback only), 8080, and 3000. Use Compose DNS for service-to-service
  connections.
- Persist data using a named local volume. Normal `down` preserves it; a
  documented explicit reset removes only this local volume.
- Store local Compose settings in root `.env`, ignored by Git, and track only a
  placeholder `.env.example`.
- Keep the local database separate from `database/compose.test.yaml`, which is
  ephemeral and reserved for automated integration tests on port 55432.
- Initialize distinct migration, runtime, and operator logins; apply migrations
  001–004 and `grants.sql` explicitly before API startup. Never let the API
  apply schema changes or connect as the migration owner.
- Use the configured Firebase project `marketing-generator-51cc0` as the local
  default, with values overrideable through `.env`. Firebase web settings are
  build-time inputs; Admin credentials are runtime-only read-only mounts.
- Configure local app image UIDs/GIDs for the developer's host identity so both
  services can read ADC while retaining non-root execution. Preserve frontend
  cache writes and do not broaden ADC file permissions.
- Do not add a Firebase emulator or claim cloud-independent sign-in in this
  iteration. A live sign-in check needs the configured Firebase project.

## Validation

Map the final implementation to the acceptance scenarios:

| Requirement | Validation |
| --- | --- |
| 002-R1 | Clean local configuration; Compose config validation; build and start all services; check frontend and API health endpoints |
| 002-R2 | Save a campaign, restart services and verify persistence; verify test service remains independently startable; verify scoped reset behavior |
| 002-R3 | Initialize a fresh volume; inspect applied schema versions and role permissions; verify API startup with runtime identity and operator CLI with operator identity |
| 002-R4 | Verify missing build values fail clearly; verify credential mounts are read-only and readable by app users; inspect image layers/config for absence of credential files |
| 002-R5 | Run focused deterministic backend/frontend tests; manually verify Firebase sign-in, membership behavior, and permitted campaign flow with the configured Firebase project |
| 002-R6 | Follow the runbook from a clean checkout and review its start, stop, logs, reset, and troubleshooting commands |

Unit and integration tests must not depend on live Firebase, model-provider, or
GCP credentials. Record manual cloud-dependent results separately from automated
test evidence.

## Rollout and recovery

This is developer-only infrastructure and does not alter production services or
existing databases. Existing developers can retain native workflows. Starting
the new stack creates a separate named local volume; stopping it preserves that
volume. The explicit local reset procedure deletes only this volume and its
campaign data. No migration of existing campaigns is performed.
