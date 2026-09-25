# 001: Workspace authorization

Status: Implemented — validated and reviewed on 2026-09-25; deployment is separate

## Problem and outcome

Before this feature, Firebase sessions identified callers, but campaign routes
shared one global repository without role enforcement. Users should access only campaigns in their
workspace and perform only actions their workspace role permits.

## Scope

Include server-side membership resolution, workspace-scoped storage operations,
route authorization, approval attribution, a dashboard workspace selector, and
an operator-run command for workspace creation and membership provisioning,
durable campaign storage, and migration of existing campaigns into a new workspace.
Exclude invitations, workspace administration UI, external publication, and broader
workload controls.

## Requirements and acceptance scenarios

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

- Given a same-origin campaign/workspace API request without a session cookie,
  then the frontend returns JSON 401 rather than redirecting the API fetch to HTML.

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

- Given a workspace switch, when old list/create/run/approval responses arrive,
  then they cannot restore old content or trigger follow-up runs; drafts are cleared.
- Given logout or session expiry, then selection and campaign content clear and
  pending discovery cannot restore access while navigation completes.
- Given membership denial, then inaccessible content clears and discovery refreshes.
- Given browser-supplied identity or role headers, then the proxy forwards only
  the verified session and selected workspace, never those identity claims.

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
model. The active backend uses workspace-bound PostgreSQL storage. The
[implementation plan](plan.md) defines the PostgreSQL adapter, transactions,
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

Validation on 2026-09-25:

| Requirement | Evidence | Result |
| --- | --- | --- |
| 001-R1 | Workspace-scoped repository and API route tests | Passed |
| 001-R2 | Four-role operation matrix, forged claims, denial without writes, schema constraints | Passed |
| 001-R3 | Verified UID, atomic audit rollback, immutable history, legacy import provenance | Passed |
| 001-R4 | Missing/invalid/expired/revoked session API tests | Passed |
| 001-R5 | Backend discovery and membership enforcement; dashboard scenarios | Backend, frontend interaction tests, and desktop/mobile browser smoke passed |
| 001-R6 | Operator provisioning, identity conflicts, suspension, role replacement, privilege separation | Passed |
| 001-R7 | Durable restart, execution recovery, full-state import, exact retry, collisions, rollback | Passed |

From `00_backend/`:

- `.venv/bin/python -m pytest -m 'not integration'`: 63 passed.
- With the disposable localhost `TEST_DATABASE_URL`, `.venv/bin/python -m pytest
  -m integration`: 42 passed against PostgreSQL 16, including migrations 001–004,
  restricted runtime/operator roles, durable API authorization and execution,
  and the export→import→restart verification rehearsal.

Firebase lookup and legacy HTTP sources are mocked in the operations tests;
PostgreSQL transactions and grants are exercised against a real disposable server.
No live Firebase accounts, deployed databases, or production campaigns were changed.
Cloud SQL private-IP/IAM behavior remains mocked. The operational steps and recovery
procedures are in [the runbook](../../database/OPERATIONS.md).

Frontend validation on 2026-09-25: `bun run test` passed 33 interaction/client/proxy
tests, `bun run lint` passed, and `bun run build` passed. Tests mock Firebase/session
and HTTP boundaries. `bun run test:browser` passed 24 Chromium checks against
the standalone production build with isolated session/API fixtures, covering
12 scenarios on desktop/mobile. See [validation and final review evidence](validation.md) for
commands, coverage boundaries, and environment recovery.

T14 documentation and T15 final review are complete. All tasks in
[tasks.md](tasks.md) are checked. The [final requirement review](validation.md#t15-final-requirement-review)
links each requirement to implementation and acceptance evidence and records the
two authentication regressions resolved before completion. Live deployment and
migration remain separate rollout work; this spec does not authorize deployment.
