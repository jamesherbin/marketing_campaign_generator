# 001: Implementation tasks

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

Execute in order; check a task only after its stated evidence exists. Requirement
IDs use the 001 prefix. Status: Implemented. Final review completed on 2026-09-25:
all tasks are complete, including the requirement/evidence review and two frontend
authentication fixes found during T15. Deployment remains separate rollout work.

## Preparation

- [x] T01: Resolve product decisions and document contracts, architecture, migration,
  validation, and recovery (001-R1–001-R7). Evidence: spec and plan review.
- [x] T02: Author migration 002 and document legacy-role handling (001-R2).
  Evidence: all four database integration tests pass against PostgreSQL 16.
  Migration 003 validation is recorded in T04.
- [x] T03a: Add pinned database/test dependencies, typed connection settings, database
  pool lifecycle/factory, and reproducible PostgreSQL 16 test setup (001-R7).
  Evidence: 15 foundation unit tests and 4 real database checks passed. The pool
  fails on connection errors and never falls back to memory.
- [x] T03b: Attach the tested lifespan and T05's durable adapter to FastAPI with T08,
  with required-migration readiness checks (001-R7). Verify the actual API refuses
  missing/unavailable/unmigrated databases and has no in-memory fallback.
  Evidence: `main.create_app` uses the PostgreSQL lifecycle and checks migrations
  001–004; both `tests/test_api_startup.py` tests passed on 2026-09-25. The prior
  integration run passed `test_actual_lifespan_rejects_unmigrated_database`.

## Schema and storage

- [x] T04: Author migration 003 and runtime/operator grants; test 001→002→003 on fresh
  and existing fixtures (001-R2, 001-R3, 001-R6, 001-R7). Verify four-role constraints,
  legacy-role abort/rollback, immutable UID snapshots, nullable email, legacy audit
  table, import ledger, and privilege separation.
  Evidence: PostgreSQL schema/upgrade/grant tests passed; deployment not performed.
- [x] T05: Introduce asynchronous repository interface and PostgreSQL adapter
  (001-R1, 001-R7). Round-trip every phase, null KPI, metadata, IDs, timestamps,
  collection order, and approvals; verify scoped consistent reads and restart survival.
  Evidence: 9 real repository tests passed, including restricted runtime-role writes,
  competing saves, partial-write rollback, and an interleaved read/write snapshot.
- [x] T06: Add versioned writes, per-campaign locking, durable phase transitions,
  and interrupted-run recovery (001-R7). Test competing requests, lock connection
  loss, failure persistence, stale writes, and existing lifecycle/ADK regressions.
  Evidence: integration tests passed concurrent-run rejection, connection-loss
  cancellation and retry, failed-run persistence and retry, and repository version
  conflicts. Existing lifecycle and ADK tests passed again on 2026-09-25.

## Authentication, authorization, and approvals

- [x] T07: Implement active-user/membership resolution and cumulative permissions
  (001-R1, 001-R2, 001-R4, 001-R6). Test verified UID lookup, ignored token roles,
  suspended entities, revoked sessions, and access removal during a phase run.
  Evidence: API tests passed the four-role matrix with misleading token roles,
  disabled users, suspended membership, session failure cases, and membership
  revocation during execution. Migration 004 provides restricted membership row
  locking without granting the runtime membership-update privileges.
- [x] T08: Add workspace discovery, required campaign workspace header, scoped
  response models, and error mapping (001-R1, 001-R2, 001-R4, 001-R5). Test the
  route/role/workspace matrix and prove no writes or runner calls on denial.
  Evidence: API tests passed workspace discovery, missing/malformed headers,
  foreign/missing campaign IDs across campaign routes, forged inputs, permission
  denials, unchanged approval state on denial, and no phase output after revocation.
- [x] T09: Commit approvals and audit events atomically with verified UID snapshots
  (001-R2, 001-R3). Test self-approval with correct role, forged actor rejection,
  duplicate decision conflicts, audit-write rollback, and immutable history.
  Evidence: API tests passed verified creator self-approval, forged actor rejection,
  concurrent duplicate decisions, and full state rollback after audit insertion
  failure; schema tests passed history immutability checks.

## Operations and migration

- [x] T10: Implement workspace-create, member-set, and member-suspend commands
  (001-R6). Test existing Firebase lookup, UID-based upsert, missing email,
  identity conflicts, explicit role replacement, repeated commands, and runtime
  credentials being unable to provision memberships.
  Evidence: operator integration tests passed Firebase UID lookup/upsert, optional
  email, identity conflicts, disabled-account refusal, explicit role replacement,
  repeat/concurrent commands, suspension, and rejection of runtime credentials.
- [x] T11: Implement old-backend export and new-workspace import/dry-run commands
  (001-R3, 001-R7). Test full-state validation, legacy history provenance, atomic
  rollback, exact retry, conflicting retry, ID collisions, and no inferred ownership.
  Document source-instance checks, write quiescence, and separate membership assignment.
  Evidence: export validation and PostgreSQL import tests passed full-state round
  trips, historical actor preservation, read-only dry runs, injected-failure
  rollback, concurrent exact retries, conflicting inputs, and ID collisions.
  Source inventory, quiescence, ownership, and recovery are documented in
  [the operations runbook](../../database/OPERATIONS.md).

## Dashboard and release evidence

- [x] T12: Implement workspace discovery proxy, header forwarding, selector, scoped
  API calls/types, and role controls (001-R1, 001-R2, 001-R5). Test zero/one/multiple
  workspaces, late responses after switching, logout, membership removal, and proxy
  refusal to forward identity claims from browser headers.
  Evidence: `bun run test` passed 31 frontend tests on 2026-09-25 across dashboard,
  API client, and real route/proxy handlers (Firebase/session boundary mocked).
  Covers zero/one/multiple workspaces, clearing drafts, late list/create/run/approval
  results and denials, all four roles, membership removal, session expiry, logout
  races/retry, scoped requests, and refusal to forward browser identity headers.
  Logout now clears content immediately and cancels pending discovery.
  `bun run lint` and `bun run build` passed; browser smoke evidence is in T13.
- [x] T13: Run full backend tests and required PostgreSQL integration checks; run
  frontend interaction tests, lint/build, and browser smoke scenarios
  (001-R1–001-R7). Record exact commands and results, including any remaining gaps.
  Evidence on 2026-09-25: 63 backend unit and 42 PostgreSQL integration tests
  passed again; 31 frontend interaction/client/proxy tests, lint, and production
  build passed. Added and ran 24 Chromium smoke checks against the standalone
  production server across desktop/mobile viewports, using isolated fixture
  sessions and API responses. See [validation.md](validation.md) for exact
  commands, scenario results, environment recovery, and coverage boundaries.
- [x] T14: Rehearse export→migrate→import→restart and recovery on disposable data;
  update READMEs, configuration examples, API docs, and lifecycle baseline references
  (001-R1–001-R7). No production deployment is part of this task.
  Evidence: automated export→file→import→membership→pool restart→verification
  rehearsal passed with mocked legacy HTTP/Firebase and real disposable PostgreSQL.
  Tests cover rollback/retry and detection of post-import drift. On 2026-09-25,
  reconciled root/backend/frontend/database READMEs, runtime configuration examples,
  API contracts, and historical baseline references. Local frontend examples now
  use the local API. Checked 41 local documentation links, all 7 API paths, argument
  syntax for all 6 operator subcommands, and `git diff --check`. The 42 passing
  PostgreSQL checks recorded in T13 include all 9 operator/import tests; no new
  database writes were needed for this documentation pass. Pool reconnection is
  the automated restart boundary; live cutover and source inventory remain rollout
  work. See [validation.md](validation.md#t14-documentation-and-rehearsal-review).
- [x] T15: Confirm evidence for every requirement, complete outstanding tasks, and
  update spec/index to Implemented only when validation is complete (001-R1–001-R7).
  Evidence: [final requirement review](validation.md#t15-final-requirement-review)
  maps all seven requirements to source and passing checks. Fixed and regression-tested
  rediscovery after session expiry and HTML redirects for sessionless API fetches.
  Final frontend validation: 33 tests, lint, build, and 24 browser checks passed;
  unchanged backend retains its 105-test evidence. Spec, plan, and index now agree
  on Implemented status; no deployment or live migration was performed.

## Recorded validation commands

From `00_backend/`:

- `.venv/bin/python -m pytest -m 'not integration'`: 63 passed on 2026-09-25.
- `TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test .venv/bin/python -m pytest -m integration`:
  42 passed on 2026-09-25 against disposable PostgreSQL 16. These are disposable
  test credentials.

No deployed database was changed. No live Firebase accounts or campaign sources
were used. T15 final feature review is complete.

From `00_frontend/`, on 2026-09-25:

- `bun run test`: 33 passed across 3 files after T15 (31 at T13), with no cloud
  credentials or live API.
- `bun run lint`: passed.
- `bun run build`: passed, including TypeScript and static page generation.
- `bun run test:browser`: 24 passed across desktop/mobile Chromium against the
  production standalone server; synthetic session/API fixtures, no live sign-in.
