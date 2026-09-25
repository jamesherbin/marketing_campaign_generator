# Campaign Database

This directory contains reproducible infrastructure for a private PostgreSQL 16
Cloud SQL instance and versioned SQL migrations for the campaign application.

## Included schema

- `users`: application identities keyed by immutable Firebase UID.
- `workspaces`: tenant boundary for campaign data.
- `workspace_members`: workspace membership with cumulative `viewer`, `editor`,
  `runner`, and `approver` roles after migration 002. Workspace administration is
  handled by the planned operator command, not an owner/admin membership role.
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
application identity:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/001_core_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/002_workspace_roles.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f migrations/003_durable_campaigns.sql
```

Apply numbered migrations in order, once per database. On an existing database
with 001 already applied, run 002 and 003. The original migration is preserved so
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
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
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

## Backend integration still required

The database connection foundation is implemented in
`00_backend/campaign/database.py`: a bounded asyncpg pool, local URL and private
Cloud SQL/IAM modes, startup probing, and bounded shutdown. Its FastAPI lifespan
factory is tested but is not yet attached to the active API. The active campaign
repository remains in memory until the authorization and orchestration cutover.

`00_backend/campaign/postgres_repository.py` now implements the asynchronous
workspace-scoped storage contract. It reads normalized state in a consistent
transaction, writes complete snapshots atomically, and rejects stale versions.
Generic saves preserve approval history and reject attempts to edit or append it.
Verified and legacy histories retain separate identity provenance in the stored
envelope. `require_campaign_schema` checks migrations 001–003 before API cutover.

The next backend work is to resolve memberships by verified UID, enforce roles,
serialize phase runs, commit approvals with state transitions atomically, and wire
the adapter into API startup. Operator commands will provision users; login will
not automatically grant membership. Database scoping is not itself authorization.

The application should never trust a workspace ID, actor ID, email, or role sent
by the browser without resolving it from the authenticated server-side identity.

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
the four supported roles, migrations 001–003, UID/history immutability, role grants,
full campaign round trips, collection ordering, workspace scoping, concurrent
version conflicts, consistent reads, and rollback of partially written state.

Stop the disposable test service from the repository root when finished:

```sh
docker compose -f database/compose.test.yaml down
```
