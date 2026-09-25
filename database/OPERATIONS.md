# Workspace operations and campaign migration

Run commands from `00_backend/` using the project's locked environment. These
commands operate with operator database credentials; they are not HTTP endpoints.
Firebase lookup verifies an existing account and does not create one.

## Configure the operator connection

Apply migrations 001 through 004 in order and apply `database/grants.sql` with
separate runtime and operator database roles, as described in [README.md](README.md).
Install dependencies with `uv sync --locked` and activate `.venv`.

The CLI reads `OPERATOR_DATABASE_*` from the process environment only. It does not
read `.env` or fall back to `DATABASE_*`. This prevents accidentally using the
application's connection. For a local PostgreSQL connection, supply
`OPERATOR_DATABASE_MODE=local` and a secret `OPERATOR_DATABASE_URL` through your
operator environment. For private Cloud SQL with ADC and IAM authentication:

```sh
export OPERATOR_DATABASE_MODE=cloud_sql
export OPERATOR_DATABASE_INSTANCE=project:region:instance
export OPERATOR_DATABASE_NAME=campaigns
export OPERATOR_DATABASE_USER=operator-service-account@project.iam
```

Keep `OPERATOR_DATABASE_URL` unset in Cloud SQL mode. Optional connection/pool
settings use the same suffixes as `DATABASE_*`, for example
`OPERATOR_DATABASE_CONNECT_TIMEOUT`. Firebase Admin uses ADC and
`GOOGLE_CLOUD_PROJECT`; the identity needs permission to look up Firebase users.
Runtime database credentials cannot pass the operator privilege check.

## Create a workspace and assign membership

First provision the desired account in Firebase through your existing account
administration process. Use its immutable Firebase UID, not an email address:

```sh
python -m campaign.manage workspace-create \
  --name 'Campaign team' --slug campaign-team --creator-uid FIREBASE_UID
python -m campaign.manage member-set \
  --workspace-id WORKSPACE_UUID --uid FIREBASE_UID --role approver
python -m campaign.manage member-suspend \
  --workspace-id WORKSPACE_UUID --uid FIREBASE_UID
```

Commands print a JSON result; use the returned workspace UUID in subsequent
commands. Creation does not grant the creator a membership. Assign one of `viewer`,
`editor`, `runner`, or `approver` explicitly. `member-set` replaces an existing role
and reactivates a suspended membership; it does not re-enable a disabled user.
`member-suspend` is repeatable and can suspend a membership even if its Firebase
account has been removed. Missing memberships produce an error.

Repeating workspace creation with the same name, slug, and creator returns the
existing active workspace. Conflicting settings are rejected. User records are
keyed by verified UID; email conflicts are rejected rather than merging identities.
Accounts without an email are supported. Disabled Firebase/application accounts
cannot be provisioned by these commands.

## Export the old in-memory campaigns

This exporter is specifically for the old API that returns complete unscoped
CampaignState records. It rejects the new workspace-scoped response format rather
than discarding ownership or verified approval identity.

Before exporting:

1. Inventory every old backend process/instance containing campaigns. A normal
   load-balanced URL does not prove all instances were captured. Arrange a direct,
   stable origin for each instance, or verify there is exactly one process.
2. Pause all writes at the deployment/access layer and wait for in-flight runs to
   finish. Do not stop or restart the old processes: their storage is in memory.
3. Prepare an authenticated Firebase session accepted by the old backend in an
   owner-only file (mode 0600), or in `CAMPAIGN_EXPORT_SESSION`. Do not put the
   cookie on the command line or in the export file.
4. Choose a private export directory outside the repository. Existing output files
   will never be overwritten.

```sh
python -m campaign.manage campaigns-export \
  --source old-instance-1 https://direct-old-instance.example \
  --session-file /secure/migration/session-cookie \
  --output /secure/migration/campaigns.json --quiesced
```

Repeat `--source INSTANCE ORIGIN` for additional processes. The session must work
for all listed sources. HTTPS is required except on localhost. The tool will not
follow redirects. It reads each source twice, aborts on any difference, merges
identical duplicate campaign IDs, and rejects conflicting duplicates. The
`--quiesced` flag acknowledges operator-enforced quiescence; the CLI does not stop
traffic, pin instances, or prove that every process has been inventoried.

Exports contain a format version, export timestamp, source inventory/counts, and
complete campaign records. Required fields, unique campaign/asset IDs, timezone-aware
timestamps, finite JSON, relational constraints, and lifecycle consistency are
validated. Running phases and completed execution without recorded approval are
rejected. Invalid legacy records must be investigated at the source; the tool does
not silently fill IDs, strip unknown fields, or normalize away invalid states.

If export fails, keep the old processes running and writes paused while correcting
the source issue. A write interrupted while saving an export may leave an incomplete
private file; use a new output path and retain the last validated export. The
importer rejects incomplete JSON.

## Dry-run, import, and verify

Provision the new migration-owner account in Firebase first. Choose a new workspace
name and slug. Do not create that workspace with `workspace-create`: the import
creates it in the same transaction as its campaigns. Generate an import UUID once:

```sh
python -c 'import uuid; print(uuid.uuid4())'
```

Save it as `CAMPAIGN_IMPORT_ID` in your operator environment and reuse it, the same
export file, owner UID, name, and slug for every retry of this migration.

```sh
python -m campaign.manage campaigns-import \
  --file /secure/migration/campaigns.json --import-id "$CAMPAIGN_IMPORT_ID" \
  --name 'Migrated campaigns' --slug migrated-campaigns --owner-uid NEW_FIREBASE_UID \
  --dry-run
python -m campaign.manage campaigns-import \
  --file /secure/migration/campaigns.json --import-id "$CAMPAIGN_IMPORT_ID" \
  --name 'Migrated campaigns' --slug migrated-campaigns --owner-uid NEW_FIREBASE_UID
python -m campaign.manage campaigns-verify \
  --file /secure/migration/campaigns.json --import-id "$CAMPAIGN_IMPORT_ID"
```

Dry-run uses a read-only transaction and performs no user, workspace, campaign, or
ledger writes. It validates identity, input, privileges, and destination collisions.
It cannot guarantee the destination remains unchanged afterward; actual import
rechecks everything transactionally.

Import creates the workspace, associates the explicitly designated user, inserts
all campaigns/history, verifies canonical state, and records the export hash under
one import UUID in a single transaction. Any failure rolls back all those writes.
Identical concurrent retries are serialized and return the original workspace.
Reusing the import UUID with changed inputs fails. A different import UUID cannot
adopt an existing workspace or overwrite existing campaign/asset IDs.

Original IDs, versions, timestamps, content, phase state, and approval displays are
preserved. Timestamp comparison uses UTC instants, so equivalent timezone offsets
match. Imported approval history is marked `legacy_unverified` with no invented
Firebase UID or historical version. The new owner is not credited with historical
approvals. New approvals continue to use verified identities in the separate audit
table. Ownership never comes from campaign metadata.

Before reopening writes, explicitly grant the designated user a workspace role:

```sh
python -m campaign.manage member-set \
  --workspace-id RETURNED_WORKSPACE_UUID --uid NEW_FIREBASE_UID --role approver
```

Restart the new API against PostgreSQL and rerun `campaigns-verify`. It checks the
campaign set, ownership, full state, and legacy approval provenance against the
export. Verify authorized access and cross-workspace denial, then reopen writes.
Verification reports drift if campaigns subsequently advance; an exact import
retry returns its original receipt and never restores old state over those changes.

## Failure recovery and rehearsal

Keep source exports and deployment backups until cutover verification succeeds.
For an interrupted/failed import, retry with the same import UUID and inputs.
Do not delete immutable history or change IDs to force a retry through. If dry-run
reports conflicting identities or IDs, investigate their source rather than
assigning a default tenant. No real accounts, workspaces, or campaign records are
created outside disposable PostgreSQL by the test suite.

The automated rehearsal in `tests/integration/test_operations.py` uses a mocked
old HTTP source, mocked Firebase lookups, real restricted operator/runtime roles,
and disposable PostgreSQL. It covers export → private file → import → membership
assignment → new connection pool → verification, plus drift detection and a
transaction-failure recovery test. Follow [test setup](README.md#disposable-postgresql-tests),
then from `00_backend/` run:

```sh
python -m pytest tests/test_migration.py
TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test \
  python -m pytest tests/integration/test_operations.py
```

This rehearsal does not test live Firebase/Cloud SQL credentials, real traffic
quiescence, or inventory of your old deployment. After new durable writes begin,
do not roll back to the global in-memory backend. Pause writes and roll forward,
or restore a database backup with deliberate reconciliation of subsequent writes.

Rehearsal evidence: the 2026-09-25 integration run passed all 42 PostgreSQL checks,
including all 9 operator/import tests. The restart rehearsal opens a new connection
pool; it does not stop a deployed API or database process. The injected ledger-write
failure proves transaction rollback and successful retry with the same import ID.
See [recorded validation](../specs/001-workspace-authorization/validation.md).
