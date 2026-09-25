# 001: Workspace authorization implementation plan

Spec: [spec.md](spec.md) · Tasks: [tasks.md](tasks.md)

Status: In progress. Migrations 002/003, role grants, the database connection
foundation, and the durable repository are implemented and tested locally. API,
authorization, orchestration, and operator-command integration remain pending.
No deployment is included.

Implementation sequencing: T03 is split into connection foundation (T03a) and
application cutover (T03b, alongside T08). The schema-readiness guard is already
tested. Cutover awaits T06–T08 so durable campaigns are introduced with membership
and role enforcement rather than an unauthenticated workspace choice.

## Architecture and dependencies

Use the existing normalized PostgreSQL schema as the durable source of campaign
state and membership. Introduce an asynchronous repository interface and a
PostgreSQL adapter; retain the in-memory adapter for isolated unit tests only.
FastAPI startup opens the database pool and shutdown closes it. Application startup
must fail clearly if database configuration or required migrations are missing;
never silently fall back to a globally shared in-memory repository.

Use asyncpg with a bounded pool. Local integration tests use PostgreSQL 16 via a
local database URL. Cloud SQL connections use the Python Cloud SQL connector with
asyncpg, private IP, and IAM database authentication. Validate dependency versions
and connector APIs during implementation, then pin compatible dependencies in the
project's dependency files. Add typed settings for connection mode, instance,
database, IAM user, pool size, and connection timeout; redact connection secrets.
No database network calls occur at module import time.

Dependencies are the existing Firebase verification, database migrations, a local
PostgreSQL test service, and a reachable Cloud SQL instance for eventual deployment.
Unit and API tests mock Firebase and use deterministic phase runners. Cloud
provisioning and live model calls are not prerequisites for implementation.

## API contract (001-R1, 001-R2, 001-R4, 001-R5)

Preserve campaign paths and bodies. Require `X-Workspace-ID: <UUID>` on every
campaign request. Add `GET /api/v1/workspaces`, returning an array of
`{workspace_id, name, slug, role}` for active memberships in active workspaces.
The corresponding same-origin frontend route is `GET /api/workspaces`.
Workspace discovery requires authentication but no workspace header.

| Operation | Minimum role | Response |
| --- | --- | --- |
| POST /api/v1/campaigns | editor | 201 CampaignState |
| GET /api/v1/campaigns | viewer | 200 CampaignState[] scoped to workspace |
| GET /api/v1/campaigns/{id} | viewer | 200 CampaignState |
| POST /api/v1/campaigns/{id}/run | runner | 200 CampaignState |
| POST /api/v1/campaigns/{id}/phases/{phase}/run | runner | 200 CampaignState |
| POST /api/v1/campaigns/{id}/execution/approval | approver | 200 CampaignState |

Verify the Firebase session first. Resolve the application user by immutable UID;
never use an email match or token roles to establish membership. Require active
user, workspace, and membership records. Disabled application users receive 403;
missing/inactive memberships and unavailable workspaces receive generic 404.
For individual campaigns, resolve the campaign within that workspace before the
role check, so foreign and missing campaign IDs return the same 404. Insufficient
role on an accessible resource returns 403. Missing/malformed workspace headers
return 422 after session verification. Invalid sessions return 401. Lifecycle or
concurrent transition conflicts return 409. Database outages return generic 503.

Perform no state mutation or runner call on denial. Recheck membership and role
inside mutation transactions; for long runs, check again before each phase and
before committing output. Reject a result if access was removed while it ran.
Lock relevant membership/status rows during short authorization/write transactions
so a committed suspension cannot be bypassed by a stale authorization read.

Add server-populated `workspace_id` and `created_by_user_id` (internal UUID) to the
campaign response envelope and frontend types. Keep the phase runner's CampaignState
payload free of authorization metadata using a response model derived from it.
Reject extra ownership/actor fields on create and approval inputs. Metadata never
overrides ownership. Existing clients must add the workspace header; deploy the
frontend and backend together. Health stays public and carries no campaign data.

## Persistence and lifecycle (001-R1, 001-R3, 001-R7)

Map the brief, all optional phase outputs, assets, activities, phase runs, metadata,
versions, timestamps, and approval history to the existing relational tables.
Preserve array positions and content asset IDs. All child reads and writes must
be reached through a workspace-scoped campaign lookup in the same operation.
Use transactions for complete state snapshots, including consistent reads.
Approval history is append-only and must not be deleted/reinserted by generic saves.

Every save checks campaign ID, workspace ID, and expected version, then increments
the version. Zero matching rows is a conflict after scoped existence is checked.
Serialize mutating operations per campaign using a PostgreSQL session advisory
lock on a dedicated connection; acquire non-blockingly and return 409 if busy.
Use a stable UUID-derived lock key. Hold the connection, not an open transaction,
while a runner executes. Release the lock in finally; discard a broken connection.
Loss of the lock connection cancels the operation and prohibits committing its
output. Version checks remain the final guard against stale writes.

Persist running status before invoking a phase and persist its output/failure in
short transactions. Clear old completion/error fields on retry. A running phase
left by a crashed worker can be marked interrupted and retried by the next explicit
run only after acquiring its advisory lock. No automatic background replay occurs.
Keep ordered phases, rejection/retry behavior, and the human approval gate intact.
There are no external publication side effects in this feature.

Move approval persistence behind one repository transaction: verify membership,
lock/check campaign version and awaiting-approval status, append an audit event,
update phase/campaign state, commit. Concurrent duplicate decisions must yield one
success and one conflict. Failure of either write rolls back both. New events store
an immutable Firebase UID snapshot as well as the internal user reference and
existing display snapshot. API approval records expose UID and provenance; clients
must not treat a display string as a verified identity.

## Additional schema changes and identity (001-R2, 001-R3, 001-R6, 001-R7)

Keep migration 001 unchanged. Migration 002 admits viewer/editor/runner/approver
and aborts on legacy owner/admin memberships until operators explicitly map them.
Add migration 003 for:

- A Firebase UID snapshot on new approval events, backfilled from referenced users
  for existing events without disabling immutability broadly. Scope any migration
  trigger adjustment to the migration transaction and restore it before commit.
- A separate immutable legacy approval history table storing campaign/workspace,
  original ordinal, actor display, decision, phase, comment, and timestamp. Do not
  invent a Firebase UID or historical campaign version absent from an export.
- An import ledger keyed by caller-supplied import UUID, with canonical export hash,
  target workspace, and target user. Ledger and imported data commit atomically.
- Nullable user email and a partial unique index for non-null normalized emails;
  Firebase UID remains the identity key. This accommodates verified Firebase users
  without email. Conflicting emails must fail explicitly, never merge accounts.

The API merges legacy history followed by new events in stable order, marking
legacy entries `identity_source: legacy_unverified` and UID null. New events use
`identity_source: firebase_verified`. Preserve all original display/timestamp data.
Runtime database grants deny mutation of audit history, identity provisioning,
workspace membership, import ledgers, and legacy history. Separate operator/import
credentials can provision users/workspaces/memberships and insert legacy imports;
migration credentials manage schema. Membership changes take effect on the next
request or phase commit. Runtime code never auto-provisions membership on login.

## Operator commands and migration (001-R6, 001-R7)

Implement `python -m campaign.manage` with subcommands:

| Command | Required inputs | Behavior |
| --- | --- | --- |
| workspace-create | name, slug, creator Firebase UID | Verify existing Firebase account, upsert user by UID, create workspace; no implicit role |
| member-set | workspace UUID, Firebase UID, one of four roles | Verify account, upsert user and active membership; explicit role replacement |
| member-suspend | workspace UUID, Firebase UID | Suspend membership without deleting history |
| campaigns-import | export file, import UUID, new workspace name/slug, new owner Firebase UID | Atomically create migration workspace and import campaigns with explicit ownership |

Commands require operator database credentials and Firebase lookup permissions,
not an application session. They are not exposed through HTTP. The new migration
user is provisioned in Firebase by the operator before import; never manufacture
an identity from metadata. Grant its selected campaign role separately via
member-set. A repeated identical workspace-create may return the existing matching
workspace; conflicting identity/slug inputs fail. Imports never adopt a preexisting
workspace except through an exact successful import-ledger retry.

Export before stopping the old backend: quiesce writes and drain running requests,
then use an operator export tool against the old authenticated campaign-list API.
Use protected file/environment input for its session rather than a command-line
secret. Because the old store is process-local, verify a single source instance;
for multiple instances, collect each snapshot and reject conflicting campaign IDs
before cutover. Abort if a consistent export cannot be established. A new process
cannot export another process's in-memory repository.

Export a versioned JSON envelope with campaign count, source metadata, and complete
CampaignState records. Protect the export as campaign data. Validate the full input
before writing: unique IDs, schema validity, relational constraints, phase states,
and preserved timestamps. Reject running phases until the old requests drain.
Report invalid rows (including currency/blank-string differences between Pydantic
and SQL) rather than silently changing data. Do not import into an existing tenant.

Import the workspace, user association, all campaign state, legacy approval history,
and ledger entry in one transaction. Use an import-ID advisory lock to serialize
retries. An exact repeat returns the original result without reinserting data;
a changed hash, owner, or workspace parameters for the same import UUID fails.
Any campaign-ID collision outside that ledger fails. Dry-run validates without
writes. After import, compare campaign IDs/counts and canonical state snapshots,
allowing only documented ownership/provenance additions.

## Frontend (001-R2, 001-R5)

Update campaign-api.ts, backend-proxy.ts, same-origin routes, dashboard, and related
types. Forward the workspace header explicitly; never forward browser-supplied
identity/role headers. Fetch accessible workspaces after login. Auto-select a sole
workspace; for multiple workspaces require selection or restore a selection still
present in the returned list. Scope saved selection to the verified user and clear
it at logout. With none, show an access-needed state and no campaign actions.

On switching workspaces, clear campaign details and drafts, cancel old requests,
and discard late responses from the previous workspace. Apply the same rule to
in-flight mutation responses; switching does not imply server-side cancellation.
Show controls according to cumulative roles while retaining backend enforcement.
On membership denial, refresh workspace discovery and clear inaccessible content.

## Validation and affected components

| Requirements | Components | Required evidence |
| --- | --- | --- |
| R1, R2, R4 | main.py, auth.py, new authorization module, API models, frontend proxy | Every campaign route × roles × two workspaces; session failures; invalid workspace; suspended membership; forged inputs; zero writes/runner calls on denial |
| R2, R3, R7 | migrations, repository interface/adapter, orchestrator | Real PostgreSQL constraint checks, snapshot round trips, concurrent runs/approvals, stale versions, rollback after audit failure, crash recovery, restart persistence |
| R5 | workspace endpoint, dashboard, campaign-api.ts | Zero/one/multiple memberships, switching with delayed responses, logout, role controls, session expiry |
| R6, R7 | management/export/import modules, database grants | Mocked Firebase provisioning, command idempotency, runtime privilege denial, export validation, exact/conflicting retries, import rollback, preserved historical actors |

R labels in this table refer to 001-R1 through 001-R7. Add focused pytest API and
PostgreSQL integration suites with isolated databases and all migrations applied.
Provide a repeatable local PostgreSQL 16 test setup; required integration checks
must fail clearly if their database is unavailable rather than silently pass.
Add frontend interaction/proxy tests using the smallest suitable test setup, plus
lint/build and a browser smoke check. Retain existing lifecycle and ADK contract
tests. Record exact commands/results in the spec when executed; these are planned
checks, not current evidence. Local pytest and a digest-pinned disposable PostgreSQL 16 service are now
available; see `database/README.md` for the commands.

## Rollout and recovery

1. Validate migrations and all tests on a disposable PostgreSQL database. Verify
   runtime/operator/migrator grants with their actual separate database roles.
2. Back up any existing durable data; resolve old owner/admin memberships explicitly.
   Provision the new Firebase user and supply deployment-specific connection inputs.
3. Quiesce the old application, export and verify all in-memory state before restart.
4. Apply 001 only to a new database, then outstanding 002/003 migrations. Import into
   the new workspace, assign membership, and verify counts and canonical state.
5. Deploy coordinated backend/frontend with database configuration and private
   connectivity. Smoke-test isolation, approvals, and persistence before reopening
   writes. This plan does not itself authorize deployment.
6. Before writes reopen, a failed cutover leaves the export and old source intact;
   repair the target and retry the import. After new durable writes, do not revert
   to the old global in-memory app. Keep writes paused and roll forward, or restore
   a database backup with reconciliation of subsequent writes under operator control.

Preserve exports/backups until verification succeeds. Do not automatically delete
legacy memberships, users, campaigns, or audit records to make a migration pass.
