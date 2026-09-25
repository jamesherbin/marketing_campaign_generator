# Working in this repository

Use the workflow in `specs/README.md` for changes to application behavior,
contracts, storage, or infrastructure.

- Read the relevant spec and implementation before editing. Existing specs may
  describe observed behavior or proposed behavior; check their status.
- Write or update requirements and observable acceptance scenarios before code.
  Assign stable requirement IDs and link implementation tasks and validation to them.
- Record scope, assumptions, and consequential unresolved decisions. Resolve routine
  choices autonomously within the user's request; ask only when a missing decision
  materially affects the outcome. No extra approval ceremony is required.
- Keep specs, implementation, and evidence in the same change. Never describe a
  draft requirement or unrun check as implemented or verified.
- Preserve ordered campaign phases, the execution approval gate, server-verified
  identity, and the distinction between prepared activities and actual publication.
- Backend Pydantic models define runtime contracts. Coordinate changes with frontend
  types, API consumers, and database mappings; do not assume these sync automatically.
- Use deterministic runners for ordinary validation. Do not require live model calls
  or cloud credentials for unit tests.
- Use focused tests for behavioral changes. Documentation-only and cosmetic changes
  can use a short change description and appropriate lightweight checks.

Start with `README.md` for development commands. `todo.md` is a backlog, not proof
of current behavior; inspect source before promoting its items into specs.
