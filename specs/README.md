# Spec-driven development

Describe intended behavior, plan the change, implement it, and attach evidence that
the behavior works. Keep these artifacts in version control alongside the code.
This workflow needs no additional framework or service.

## Project principles

- CampaignState is the shared campaign contract; backend, frontend, agents, and
  persistence must agree on its meaning.
- Execution pauses for human approval. Prepared activities do not mean publication
  occurred. Monitoring must distinguish missing data from measured zero.
- Authentication does not imply campaign ownership or permission to approve.
- Deterministic runners make development reproducible; ADK integrations require
  separate contract and failure validation.
- Record known gaps honestly, including historical storage limitations and incomplete coverage.

## Workflow

1. Inspect the relevant source, tests, and existing specs. Select the next unused
   numeric directory, such as `002-durable-storage`.
2. Copy `templates/spec.md`, `templates/plan.md`, and `templates/tasks.md` into it.
   Define the problem, scope, stable requirement IDs, and Given/When/Then scenarios.
3. Resolve decisions needed for implementation. Record assumptions and tradeoffs in
   the plan, including API, model, UI, storage, and compatibility impacts.
4. Break the plan into small tasks linked to requirement IDs. Implement and run
   focused checks; include failure cases and meaningful boundaries.
5. Record exact commands, results, and remaining gaps in the spec's evidence table.
   Update docs and contracts in the same change. Mark implemented only when every
   in-scope requirement has evidence and no blocking task remains.

Statuses: **Draft** (proposal with possible open decisions), **Ready** (actionable
scope and plan), **In progress**, **Implemented** (validated), **Superseded** (link
replacement). **Baseline** documents observed existing behavior and can have
explicit coverage gaps; it is not a claim that every behavior is tested.

Use a single spec file for a small behavioral change if separate plan/tasks files
would add no value. Typo fixes and purely cosmetic changes do not need feature specs.
For bugs, specify the correct behavior and a reproducer before changing code.
For intentional behavior changes, update the governing spec and retain its IDs;
Git records history. Link superseding specs when a requirement is retired.

## Index

| Spec | Status | Purpose |
| --- | --- | --- |
| [000: Campaign lifecycle](000-campaign-lifecycle/spec.md) | Baseline | Existing behavior and test coverage |
| [001: Workspace authorization](001-workspace-authorization/spec.md) | Implemented | Workspace isolation, roles, durable storage, and operator migration validated; deployment separate |
| [002: Local development stack](002-local-development-stack/spec.md) | Implemented | Repeatable local Docker Compose setup with persistent PostgreSQL and Firebase configuration ([quick start](../LOCAL_DEVELOPMENT.md#docker-compose-quick-start)) |
| [003: Color theme](003-color-theme/spec.md) | Implemented | Light/dark/system palettes with browser-local preference and desktop/mobile validation |
| [004: Agent/backend integration](004-agent-backend-integration/spec.md) | Implemented | ADK integration, canonical outputs, isolated sessions, and lifecycle safeguards validated; live deployment separate |

`todo.md` remains the broader backlog. Its authentication items predate parts of
the Firebase implementation; verify each item against code before scheduling it.
The active API uses PostgreSQL with migrations 001–004 and runtime grants; see
[database setup](../database/README.md).

## Validation

From `00_backend/`, with dependencies installed:

```sh
.venv/bin/python -m pytest tests/test_orchestrator.py
.venv/bin/python -m pytest -m 'not integration'
```

For the full suite including required PostgreSQL checks, use the
[disposable test database setup](../database/README.md#disposable-postgresql-tests).

For frontend changes, from `00_frontend/`:

```sh
bun run lint
bun run build
```

Choose checks based on affected behavior. Builds do not prove authorization or
lifecycle correctness. Add API/integration checks when changing those boundaries.
In review, report the spec path, covered IDs, evidence, and unresolved limitations.
