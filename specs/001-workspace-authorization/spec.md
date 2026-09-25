# 001: Workspace authorization

Status: In progress — schema and durable repository implemented; API cutover pending

## Problem and outcome

Firebase sessions identify callers, but campaign routes currently share one global
repository and do not enforce roles. Users should access only campaigns in their
workspace and perform only actions their workspace role permits.

## Scope

Include server-side membership resolution, workspace-scoped storage operations,
route authorization, approval attribution, a dashboard workspace selector, and
an operator-run command for workspace creation and membership provisioning,
durable campaign storage, and migration of existing campaigns into a new workspace.
Exclude invitations, workspace administration UI, external publication, and broader
workload controls.

## Proposed requirements and acceptance scenarios

### 001-R1: Tenant isolation

- Given members of different workspaces, when they list campaigns, then each sees
  only campaigns belonging to the selected workspace with verified membership.
- Given a campaign in another workspace, when a caller retrieves, runs, or approves
  it, then the API returns 404 without disclosing its state or changing it.
- Given a create request, when saved, then its workspace is server-validated and
  its creator is the authenticated Firebase UID.

### 001-R2: Workspace roles

Agreed cumulative permissions:

| Role | Permissions |
| --- | --- |
| viewer | List and retrieve |
| editor | Viewer permissions plus create |
| runner | Editor permissions plus run campaign or individual phase |
| approver | Runner permissions plus approve and reject |

- The database accepts only `viewer`, `editor`, `runner`, and `approver` as
  workspace membership roles. Workspace administration uses the operator command;
  `owner` and `admin` are not assignable workspace roles in this version.
- Given a campaign creator with the approver role in that workspace, when they
  approve their own campaign, then self-approval is permitted.
- Given existing `owner` or `admin` memberships, when the role constraint migration
  runs, then it stops without changing data until an operator explicitly reassigns
  those memberships to supported roles. No automatic permission mapping is assumed.

- Given a workspace member lacking an operation's permission, when attempting it,
  then the API returns 403 before invoking a runner or mutating state.
- Given forged role or membership values in browser input, when authorization is
  evaluated, then only trusted server-side membership records determine access.

### 001-R3: Approval attribution

- Given an authorized approval, when committed, then an immutable audit event stores
  the verified Firebase UID, timestamp, decision, campaign, and workspace.
- Given failure to write the audit event, when approving, then no approval state
  transition commits. Display names and emails do not replace the immutable UID.

### 001-R4: Authentication regression protection

- Given missing, invalid, expired, or revoked sessions, when any campaign operation
  is requested, then it returns 401 and performs no state change.

### 001-R5: Workspace selection

- Given a user with one accessible workspace, when they open the dashboard, then
  that workspace is selected automatically.
- Given a user with multiple accessible workspaces, when they use the dashboard,
  then a workspace selector lets them choose their active workspace.
- Given an active workspace, when the dashboard makes a campaign API request,
  then the request identifies that workspace and the backend verifies membership
  before granting access.
- Given a user without workspace membership, when they open the dashboard, then
  no campaign workspace is available and they cannot grant themselves access.

### 001-R6: Operator-managed membership

- Given an authorized operator, when they run the management command, then they
  can create a workspace and assign an existing Firebase user a role within it.
- Given a provisioned membership, when a campaign request is authorized, then
  the backend resolves the user's membership and role from PostgreSQL using the
  verified Firebase UID on every request.
- Given an ordinary application user, when they use the dashboard or campaign
  API, then they cannot provision their own membership or elevate their role.

### 001-R7: Durable storage and existing campaign migration

- Given campaigns saved in PostgreSQL, when the backend restarts, then their
  campaign state and workspace ownership remain available to authorized members.
- Given existing campaigns exported before the in-memory backend is stopped,
  when an operator imports them, then a new workspace is created for those campaigns
  and ownership is assigned to the newly provisioned user designated for migration.
- The operator supplies the new user's verified Firebase UID and the new workspace's
  name and slug at migration time. Ownership must not be inferred from campaign
  metadata. The operator provisions workspace membership through the management
  command; migration ownership does not introduce an `owner` role.
- Given a failed or repeated import, when migration is retried, then no partial
  campaign records or duplicate campaigns are created. Existing campaign IDs and
  state are preserved; migration ownership must not replace historical approval
  actors or imply that the new user made historical approvals.

## Contracts and dependencies

Build on `database/migrations/001_core_schema.sql` and its workspace membership
model. The active backend still uses InMemoryCampaignRepository. The [implementation plan](plan.md) defines the PostgreSQL adapter, transactions,
API contract, and coordinated frontend changes; SQL files alone do not provide
runtime isolation. Do not trust a client-supplied workspace without
resolving membership from the verified UID.

## Resolved decisions

- Workspace roles are cumulative: viewer, editor, runner, approver. Creators may
  approve their own campaigns when they have the approver role. Remove owner/admin
  from assignable workspace roles; administration remains an operator function.

- Users select their active workspace in the dashboard; a single accessible
  workspace is selected automatically. Campaign API requests identify the selected
  workspace, and the backend verifies membership on every request.
- Operators create workspaces and assign existing Firebase users and roles through
  a management command. Membership is stored in PostgreSQL. Users cannot grant
  themselves access. Workspace administration UI remains out of scope.
- The implementation plan defines the API contract and management command
  details consistent with these requirements.
- Durable storage ships in this feature.
- Existing campaigns migrate into a newly created workspace and are assigned to
  a new user. The operator provides the account and workspace details at migration
  time; production identifiers are not required to finish the implementation plan.

## Open decisions

No remaining blocking decisions are identified. Technical choices and migration
behavior are recorded in [plan.md](plan.md); ordered implementation and validation
work is recorded in [tasks.md](tasks.md). Deployment-specific identities and
connection values are supplied at rollout time.

## Evidence

| Requirement | Planned validation | Result |
| --- | --- | --- |
| 001-R1 | Two-workspace API tests across every campaign route | Not implemented/run |
| 001-R2 | Role-by-operation matrix; forged membership; no mutation or runner calls on denial | Not implemented/run |
| 001-R3 | Verified UID assertion and transaction rollback on audit failure | Not implemented/run |
| 001-R4 | Session failure matrix across every campaign route | Not implemented/run |
| 001-R5 | Dashboard scenarios for zero, one, and multiple workspaces; selected workspace propagation and backend membership enforcement | Not implemented/run |
| 001-R6 | Management command provisioning tests; PostgreSQL membership lookup; denial of self-provisioning and role elevation | Not implemented/run |
| 001-R7 | Restart persistence; import into new workspace with explicit user ownership; failed/repeated import and historical actor preservation | Not implemented/run |

Implementation evidence on 2026-09-24:

- From `00_backend/`, `.venv/bin/python -m pytest -m 'not integration'`: 35 passed, including 15 database settings/lifecycle
  checks and existing auth, lifecycle, configuration, and agent tests.
- With the disposable localhost `TEST_DATABASE_URL`, `.venv/bin/python -m pytest
  -m integration`: 18 passed against PostgreSQL 16. Covers migrations 001–003,
  legacy-role abort/retry, immutable UID snapshots/history, optional emails,
  restricted runtime/operator grants, schema readiness, complete campaign round
  trips across pool restarts, workspace isolation, stale/concurrent writes,
  failed-child rollback, and consistent reads during a concurrent save.
- `uv pip check --cache-dir /tmp/campaign-uv-cache`: all 134 installed packages
  compatible. Runtime and development dependencies are pinned in `uv.lock`.
- Database mode/settings, bounded pools, safe startup errors, shutdown cleanup, and
  an independently tested FastAPI lifespan factory are implemented. Cloud SQL
  private-IP/IAM connection behavior is mocked; no live Cloud SQL call was made.

These checks establish the schema, connection foundation, and durable storage
adapter, not full feature completion. Generic saves cannot alter approval history.
Atomic approval decisions, phase execution locks/recovery, API authorization,
operator commands, and frontend integration remain pending. The active API still
uses memory until the coordinated authorization/orchestration cutover. Migrations
were applied only to disposable integration databases, not a deployed database.

Next step: implement T06–T08 (durable orchestration and API authorization), then
attach the adapter, database lifespan, and schema-readiness guard. See unchecked tasks.
This work does not authorize infrastructure deployment.
