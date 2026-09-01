# Campaign Database

This directory contains reproducible infrastructure for a private PostgreSQL 16
Cloud SQL instance and versioned SQL migrations for the campaign application.

## Included schema

- `users`: application identities keyed by immutable Firebase UID.
- `workspaces`: tenant boundary for campaign data.
- `workspace_members`: workspace membership and application roles.
- `campaigns`: durable campaign state with ownership and optimistic versioning.
- `campaign_briefs`: the `CampaignBrief` fields.
- `planning_outputs`: the optional `PlanningOutput` phase result.
- `development_outputs` and `content_assets`: `DevelopmentOutput` and its assets.
- `execution_outputs` and `scheduled_activities`: `ExecutionOutput` and its activities.
- `monitoring_outputs`: the optional `MonitoringOutput` phase result.
- `phase_runs`: one `PhaseRun` per campaign lifecycle phase.
- `approval_events`: append-only approval audit records tied to verified users.

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
```

Do not place a database password in Terraform variables or source control. Prefer
Cloud SQL IAM database authentication and a short-lived connector token. Record
every applied migration in deployment automation before adding later migrations.

## Backend integration still required

Provisioning this database does not switch the FastAPI application away from its
in-memory repository. The next backend change should:

1. Add a PostgreSQL driver and connection pool using the Cloud SQL connector.
2. Upsert `users` after Firebase token verification.
3. Resolve workspace membership from the verified Firebase UID.
4. Scope every campaign query by `workspace_id`.
5. Update campaigns with `WHERE campaign_id = ? AND workspace_id = ? AND version = ?`.
6. Insert approval events and update campaign state in the same transaction.

The application should never trust a workspace ID, actor ID, email, or role sent
by the browser without resolving it from the authenticated server-side identity.
