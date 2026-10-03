# Campaign Database

This directory contains reproducible infrastructure for a private PostgreSQL 16
Cloud SQL instance and versioned SQL migrations for the campaign application.

## Included schema

- `users`: application identities keyed by immutable Firebase UID.
- `workspaces`: tenant boundary for campaign data.
- `workspace_members`: workspace membership with cumulative `viewer`, `editor`,
  `runner`, and `approver` roles after migration 002. Workspace administration is
  handled by the operator command, not an owner/admin membership role.
- `campaigns`: durable campaign state with ownership and optimistic versioning.
- `campaign_briefs`: the `CampaignBrief` fields.
- `planning_outputs`: the optional `PlanningOutput` phase result.
- `development_outputs` and `content_assets`: `DevelopmentOutput` and its assets.
- `execution_outputs` and `scheduled_activities`: `ExecutionOutput` and its activities.
- `monitoring_outputs`: the optional `MonitoringOutput` phase result.
- `phase_runs`: one `PhaseRun` per campaign lifecycle phase.
- `approval_events`: append-only approval audit records tied to verified users.
- `legacy_approval_history`: immutable imported approval displays without invented identities.
- `campaign_imports`: immutable import identities and hashes for safe retries.
- `schema_migrations`: required schema versions, initialized by migration 003.

The relational schema follows the Pydantic models in `00_backend/campaign/models.py`.
Dynamic mappings (`metadata`, `media_plan`, `budget_by_channel`, and `kpis`) remain
JSONB, while nested model collections use relational child tables. List positions
are stored where ordering is significant.

## Provision Cloud SQL

Prerequisites:

- Terraform 1.6 or newer.
- A Google Cloud project with billing enabled.
- Application Default Credentials with permission to manage Cloud SQL, networking,
  IAM bindings, and project services.
- A dedicated backend service account created outside this module.

Create a local variables file (it is safe to commit only the example):

```sh
cd database
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=database.tfplan
terraform apply database.tfplan
```

The instance has no public IPv4 address. It uses private services access,
encrypted connections, automated backups, point-in-time recovery, deletion
protection, and IAM database authentication. The backend must have network access
to the output VPC, for example through Cloud Run Direct VPC egress.

Terraform state can contain sensitive infrastructure data. Use a protected remote
Google Cloud Storage backend with versioning, encryption, and tightly scoped IAM
before team or production use. Do not commit local state or plan files.

## Apply migrations

Terraform creates the instance and empty database but intentionally does not run
SQL. Apply migrations as a separate deployment step from a trusted runner that can
reach the private VPC, using a dedicated migration identity rather than the runtime
application identity. Run the commands below from `database/`; supply
`MIGRATION_DATABASE_URL` through a protected environment using that migration
identity, not the API runtime login:

```sh
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/001_core_schema.sql
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/002_workspace_roles.sql
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/003_durable_campaigns.sql
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/004_authorization_locks.sql
```

Apply numbered migrations in order, once per database. On an existing database
with 001 already applied, run 002 through 004. The original migration is preserved so
existing installations have the same upgrade path as fresh databases.

Migration 002 adds `runner` and removes `owner`/`admin`. It runs transactionally
and stops before changing the constraint if legacy memberships exist. Inspect
them with `SELECT workspace_id, user_id, role FROM workspace_members WHERE role
IN ('owner', 'admin');` and explicitly assign each a supported role before retrying.
The old constraint permits viewer/editor/approver; a desired runner assignment
can be made after migration 002. No automatic legacy-role mapping is performed.

Schedule the migration when its exclusive membership-table lock is acceptable.
If it fails, the transaction rolls back. After success, reverting to the old
constraint requires explicitly reassigning any runner memberships first; use a
reviewed forward migration rather than rerunning 001.

Migration 003 requires 002 and runs in one transaction. It makes email optional,
freezes Firebase UIDs, backfills approval UID snapshots from referenced users,
and adds legacy history, import bookkeeping, and schema versions. The approval
update trigger is disabled only inside that migration transaction for the backfill
and restored before commit. Subsequent approval inserts derive their UID snapshot
from the actor's user record and reject contradictory supplied UIDs.

Apply the role grants separately with the migration/schema-owner identity, using
existing, distinct runtime and operator roles:

```sh
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -v runtime_role=campaign_runtime -v operator_role=campaign_operator -f grants.sql
```

Replace these example database role names with the provisioned roles. Neither
role may own the schema, be a superuser, or inherit broader grants. Runtime can
read identity/membership records and write campaign state and new approvals;
it cannot provision membership, rewrite audit records, or import legacy history.
Operator can provision users/workspaces/memberships and insert imported campaign
data, legacy history, and import records. Migration credentials remain separate.
The script revokes PUBLIC table access and CREATE on the application's public
schema; use it only in the dedicated campaign database. It does not create logins,
configure IAM, or authorize deployment.

Do not place a database password in Terraform variables or source control. Prefer
Cloud SQL IAM database authentication and a short-lived connector token. Record
every applied migration in deployment automation before adding later migrations.

## Operator commands and migration

See [OPERATIONS.md](OPERATIONS.md) for workspace/member provisioning, legacy
exports, read-only import previews, atomic imports, verification, and recovery.
Commands require explicit `OPERATOR_DATABASE_*` settings and use existing Firebase
UIDs. They do not provision cloud infrastructure or create Firebase accounts.

## Backend integration

The database connection foundation is implemented in
`00_backend/campaign/database.py`: a bounded asyncpg pool, local URL and private
Cloud SQL/IAM modes, startup probing, and bounded shutdown. Its FastAPI lifespan
factory and the active API lifespan are tested. The API now requires PostgreSQL,
schema versions 001–004, and runtime authorization grants; it has no memory fallback.

`00_backend/campaign/postgres_repository.py` now implements the asynchronous
workspace-scoped storage contract. It reads normalized state in a consistent
transaction, writes complete snapshots atomically, and rejects stale versions.
Generic saves preserve approval history and reject attempts to edit or append it.
Verified and legacy histories retain separate identity provenance in the stored
envelope. `require_campaign_schema` checks migrations 001–004 at startup.

The API resolves memberships by verified UID, enforces cumulative roles, serializes
phase runs, and commits approvals with state transitions atomically. Migration 004
provides a restricted function for locking membership rows without granting runtime
membership-write privileges. Operator commands provision users and memberships;
login does not automatically grant access.

The application should never trust a workspace ID, actor ID, email, or role sent
by the browser without resolving it from the authenticated server-side identity.

## Persistent local development PostgreSQL

Local app development uses a separate PostgreSQL service from the disposable
integration-test service below. It binds only to `127.0.0.1:5433` and persists
campaigns in its own named Docker volume. Do not point the API at the test
service on port `55432`.

From the repository root, create the ignored Compose environment file if it does
not exist, then replace each example password with a unique local value:

```sh
[ -f .env ] || cp .env.example .env
```

Start PostgreSQL and apply migrations 001–004 plus application grants:

```sh
docker compose -f compose.local.yaml up -d --wait postgres
docker compose -f compose.local.yaml run --rm migrate
```

The first database initialization creates separate `campaign_migrator`,
`campaign_runtime`, and `campaign_operator` logins. The image bootstrap superuser
is disabled after creating them. The migration command is safe to repeat after
version 4; it applies migration 004 when the database is at version 3, and stops
on an ambiguous partial schema. The API must use the runtime login and management
commands must use the operator login. Never use bootstrap or migrator credentials
for application requests.

Normal `docker compose ... down` preserves the local database volume. Delete the
development volume only when intentionally resetting local campaign data. This
service is for local development; it is not a backup or production database.

## Disposable PostgreSQL tests

From the repository root, start Docker and run:

```sh
docker compose -f database/compose.test.yaml up -d --wait
```

This digest-pinned PostgreSQL 16 service binds only to localhost port 55432 and
stores data in temporary memory-backed storage. Its committed credentials are for
this disposable local service only. It must not be used for real campaign data.

From `00_backend/`, install the locked runtime and development dependencies:

```sh
uv sync --locked
```

Run tests without a database:

```sh
.venv/bin/python -m pytest -m 'not integration'
```

Run the full suite including PostgreSQL checks:

```sh
TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test \
  .venv/bin/python -m pytest
```

Integration tests require this explicit local test database and fail when it is
unavailable. Each test creates and drops its own randomly named database; the
server user therefore needs CREATEDB and CREATEROLE (the disposable service supplies
a test superuser). Grant tests use isolated non-superuser runtime/operator roles,
then remove their grants and roles. The tests apply migrations themselves and
never use the application's DATABASE_URL. They currently cover pool persistence,
the four supported roles, migrations 001–004, UID/history immutability, role grants,
full campaign round trips, collection ordering, workspace scoping, concurrent
version conflicts, consistent reads, and rollback of partially written state. API
tests also cover session/role enforcement, approval atomicity, interrupted runs,
and revoked access. ADK-specific API tests use real adapters with simulated event
streams to verify approval/rejection retries, durable readback through a fresh API
lifespan, safe provider/schema/semantic failures, and cleanup after interrupted
runs, without live model calls. Operator tests rehearse export/import, restart verification,
transaction rollback, and exact retry. See [validation evidence](../specs/001-workspace-authorization/validation.md).

Stop the disposable test service from the repository root when finished:

```sh
docker compose -f database/compose.test.yaml down
```
