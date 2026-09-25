# 001: Implementation tasks

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

Execute in order; check a task only after its stated evidence exists. Requirement
IDs use the 001 prefix. Status: In progress. Checked foundation tasks do not imply API integration.

## Preparation

- [x] T01: Resolve product decisions and document contracts, architecture, migration,
  validation, and recovery (001-R1–001-R7). Evidence: spec and plan review.
- [x] T02: Author migration 002 and document legacy-role handling (001-R2).
  Evidence: all four database integration tests pass against PostgreSQL 16.
  Migration 003 validation remains in T04.
- [x] T03a: Add pinned database/test dependencies, typed connection settings, database
  pool lifecycle/factory, and reproducible PostgreSQL 16 test setup (001-R7).
  Evidence: 15 foundation unit tests and 4 real database checks passed. The pool
  fails on connection errors and never falls back to memory.
- [ ] T03b: Attach the tested lifespan and T05's durable adapter to FastAPI with T08,
  with required-migration readiness checks (001-R7). Verify the actual API refuses
  missing/unavailable/unmigrated databases and has no in-memory fallback. This is
  deferred to T08 so the new store is introduced with membership/role enforcement.
  The schema-readiness guard itself is implemented and tested.

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
- [ ] T06: Add versioned writes, per-campaign locking, durable phase transitions,
  and interrupted-run recovery (001-R7). Test competing requests, lock connection
  loss, failure persistence, stale writes, and existing lifecycle/ADK regressions.

## Authentication, authorization, and approvals

- [ ] T07: Implement active-user/membership resolution and cumulative permissions
  (001-R1, 001-R2, 001-R4, 001-R6). Test verified UID lookup, ignored token roles,
  suspended entities, revoked sessions, and access removal during a phase run.
- [ ] T08: Add workspace discovery, required campaign workspace header, scoped
  response models, and error mapping (001-R1, 001-R2, 001-R4, 001-R5). Test the
  route/role/workspace matrix and prove no writes or runner calls on denial.
- [ ] T09: Commit approvals and audit events atomically with verified UID snapshots
  (001-R2, 001-R3). Test self-approval with correct role, forged actor rejection,
  duplicate decision conflicts, audit-write rollback, and immutable history.

## Operations and migration

- [ ] T10: Implement workspace-create, member-set, and member-suspend commands
  (001-R6). Test existing Firebase lookup, UID-based upsert, missing email,
  identity conflicts, explicit role replacement, repeated commands, and runtime
  credentials being unable to provision memberships.
- [ ] T11: Implement old-backend export and new-workspace import/dry-run commands
  (001-R3, 001-R7). Test full-state validation, legacy history provenance, atomic
  rollback, exact retry, conflicting retry, ID collisions, and no inferred ownership.
  Document source-instance checks, write quiescence, and separate membership assignment.

## Dashboard and release evidence

- [ ] T12: Implement workspace discovery proxy, header forwarding, selector, scoped
  API calls/types, and role controls (001-R1, 001-R2, 001-R5). Test zero/one/multiple
  workspaces, late responses after switching, logout, membership removal, and proxy
  refusal to forward identity claims from browser headers.
- [ ] T13: Run full backend tests and required PostgreSQL integration checks; run
  frontend interaction tests, lint/build, and browser smoke scenarios
  (001-R1–001-R7). Record exact commands and results, including any remaining gaps.
- [ ] T14: Rehearse export→migrate→import→restart and recovery on disposable data;
  update READMEs, configuration examples, API docs, and lifecycle baseline references
  (001-R1–001-R7). No production deployment is part of this task.
- [ ] T15: Confirm evidence for every requirement, complete outstanding tasks, and
  update spec/index to Implemented only when validation is complete (001-R1–001-R7).
