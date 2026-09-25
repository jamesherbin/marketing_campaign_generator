# 001: Validation and final review evidence

Completed locally on 2026-09-25. T13 validation, T14 documentation, and T15 final
review are complete. Spec status: Implemented. Deployment is not included.

## Commands and results

From `00_backend/`:

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -m 'not integration'` | 63 passed, 42 deselected |
| `TEST_DATABASE_URL=postgresql://campaign_test:campaign_test_local_only@127.0.0.1:55432/campaign_test .venv/bin/python -m pytest -m integration` | 42 passed, 63 deselected |

These are disposable test credentials. PostgreSQL 16 ran through
`database/compose.test.yaml`; each integration fixture uses an isolated database.
The suite covers migrations 001–004, runtime/operator grants, API roles and tenant
isolation, approval attribution and rollback, durable phase execution/recovery,
repository restart persistence, and provisioning/import/recovery (001-R1–001-R7).
Firebase and model boundaries are mocked; no deployed database was modified.

From `00_frontend/`:

| Command | Result |
| --- | --- |
| `bun run test` | 33 passed across 3 files after the T15 fixes (31 at T13) |
| `bun run lint` | Passed |
| `bun run build` | Passed; production compilation, TypeScript, and static generation |
| `bunx playwright install chromium --only-shell` | Installed pinned Chromium headless shell for Playwright 1.63.0 |
| `bun run test:browser` | 24 passed (12 scenarios × desktop/mobile), T15 final run 9.7 seconds |

The frontend interaction tests cover workspace selection, scoped requests, role
controls, late list/create/run/approval results, stale denials, membership removal,
session expiry, logout races/retry, and proxy header allowlisting (001-R1/R2/R4/R5).

## Browser smoke scenarios

`00_frontend/tests/browser/workspaces.spec.ts` runs against the actual standalone
Next.js production server on `127.0.0.1:3100`. The launcher copies generated static
assets into the same layout as the production container. Chromium projects use
Desktop Chrome and Pixel 7 viewport/device settings.

| Scenario | Evidence |
| --- | --- |
| No session | Real middleware redirects to the rendered login page |
| Zero memberships | Access-needed state; no campaign fetch or create controls |
| Sole membership, each of four roles | Auto-selection and cumulative create/run/approval controls |
| Multiple memberships | Explicit selection; workspace-specific content; discarded draft |
| Late run response after switching | New workspace stays selected and old output stays hidden |
| Create→run→approval→monitoring | Scoped request bodies/headers, approval gate, explicit review note, follow-up run, null KPI displayed as awaiting data |
| Removed membership | Denied request clears campaign content and refreshes discovery |
| Expired session | Campaign content clears and browser reaches login |
| Logout | Selection clears, no rediscovery, and protected-page revisit redirects |

Desktop/mobile screenshots of approval controls, switched workspaces, and the
completed fixture campaign are saved under ignored `00_frontend/test-results/`.
Desktop approval and mobile completion screenshots were visually inspected; the
workspace selector, actions, phase rail, and outputs remain usable. Traces and
failure screenshots are retained automatically if a future run fails.

The browser suite uses a synthetic cookie only in an isolated test context and
intercepts browser API requests with deterministic fixtures. It does not exercise
live Google sign-in, Firebase session validation, or a browser-to-PostgreSQL round
trip. Those server boundaries have separate proxy and PostgreSQL API test evidence;
live deployment smoke tests remain rollout work. No application authentication
bypass, test route, or live account provisioning was added.

## Environment issues and recovery

- The connected Browser runtime reported no available browsers. The repeatable
  headless Playwright suite provided the browser validation instead.
- Sandbox restrictions blocked the initial PostgreSQL connection and local browser
  server port. Both passed when rerun with approved local-process/network access.
- A rebuild was initially started while the browser server was using the same
  generated output, invalidating that attempt. The build also hit a sandbox port
  failure cached by Turbopack. The failed generated directory was moved aside;
  a clean build with approved worker-port access succeeded. The final browser run
  used the completed standalone build with no concurrent rebuild.
- The build reported an old Browserslist data warning, but compilation succeeded.

Run build and browser validation sequentially. Playwright starts and stops its own
server, refuses to reuse another process on port 3100, and closes isolated browser
contexts after each test. The pre-existing disposable PostgreSQL service was left
running; integration fixtures clean up their own test databases and roles.

## T14 documentation and rehearsal review

Completed on 2026-09-25 for 001-R1–001-R7. Root/backend/frontend/database READMEs
now describe durable startup, migrations 001–004 and grants, separate credentials,
Firebase authentication, workspace discovery and roles, request headers/bodies,
response ownership/provenance, and API errors. Removed obsolete in-memory API and
pending-cutover claims; preserved the explicitly historical lifecycle baseline.
The frontend example now uses `API_URL=http://localhost:8080`, avoiding accidental
local-to-deployed API requests. Backend examples call the locked virtual environment
and identify the required runtime grants. The operational runbook distinguishes
new workspace provisioning from import-created workspaces and documents recovery.

Lightweight checks for this documentation/configuration-example change:

- Checked 41 relative documentation file links across 11 documents: all resolved.
- Compared the 7 documented API paths against `main.app.openapi()`: matched.
- Parsed example arguments for all 6 `campaign.manage` subcommands: accepted.
- `python -m campaign.manage --help` and `git diff --check`: passed.

The existing T13 run (42 PostgreSQL checks, including 9 operator/import checks)
provides the migration rehearsal evidence. In particular:

- `test_export_import_restart_rehearsal_and_drift_detection` exports mocked old
  HTTP data to a private file, loads/imports it into migrated disposable PostgreSQL,
  assigns membership, verifies canonical state through a new pool, detects later
  changes, and proves an exact retry does not overwrite newer data.
- `test_import_failure_rolls_back_everything_then_retry_succeeds` injects a ledger
  failure, checks rollback of imported rows, removes the injected failure, and
  successfully retries the same import.

The fixture applies migrations before importing; restart means a new connection
pool, not terminating a live API/database process. No production migration, live
Firebase lookup, or infrastructure deployment was performed. Runtime code was not
changed by T14, so the already-passing behavioral suite was not rerun for this
README/configuration-example pass.

## T15 final requirement review

Completed on 2026-09-25. Each requirement was compared with the implementation,
acceptance tests, and the recorded successful runs. All implementation tasks are
complete. The following map makes the final evidence traceable; paths are relative
to this document.

| Requirement | Implementation reviewed | Acceptance evidence |
| --- | --- | --- |
| 001-R1 | [Membership resolution](../../00_backend/campaign/authorization.py), [scoped service](../../00_backend/campaign/service.py), [repository](../../00_backend/campaign/postgres_repository.py) | [API role/foreign-ID matrix](../../00_backend/tests/integration/test_api.py) and [repository isolation/round trips](../../00_backend/tests/integration/test_postgres_repository.py); create attribution follows the verified UID's internal user row |
| 001-R2 | Cumulative role ranks, service authorization before mutation, [role migration](../../database/migrations/002_workspace_roles.sql), dashboard controls | API four-role matrix, forged claims, self-approval, denial without state changes; [legacy-role abort tests](../../00_backend/tests/integration/test_database.py); frontend role controls at all four roles |
| 001-R3 | [Atomic approval transaction](../../00_backend/campaign/service.py), [immutable identity/history schema](../../database/migrations/003_durable_campaigns.sql), import provenance | API verified self-approval and audit-failure rollback tests; [schema constraints](../../00_backend/tests/integration/test_schema.py); [import history preservation](../../00_backend/tests/integration/test_operations.py) |
| 001-R4 | [Firebase verification](../../00_backend/campaign/auth.py), [frontend middleware](../../00_frontend/proxy.ts), [server proxy](../../00_frontend/lib/backend-proxy.ts) | API missing/invalid/expired/revoked-session matrix, [proxy tests](../../00_frontend/tests/proxy.test.ts), real standalone server JSON 401 checks in [browser smoke](../../00_frontend/tests/browser/workspaces.spec.ts) |
| 001-R5 | [Workspace dashboard](../../00_frontend/app/page.tsx), [scoped API client](../../00_frontend/lib/campaign-api.ts), workspace discovery | [Dashboard tests](../../00_frontend/tests/dashboard.test.tsx), [client tests](../../00_frontend/tests/campaign-api.test.ts), proxy and desktop/mobile browser checks: zero/one/multiple workspaces, stale responses, roles, logout, expiry, revoked access |
| 001-R6 | [Operator commands](../../00_backend/campaign/manage.py), [provisioning service](../../00_backend/campaign/operations.py), [separate grants](../../database/grants.sql) | Operator tests cover lookup/upsert, role replacement, suspension, repeat commands, identity conflicts, disabled accounts, and refusal of runtime credentials; no provisioning HTTP route exists |
| 001-R7 | Durable repository/service, [export validation](../../00_backend/campaign/migration.py), transactional import/ledger, [runbook](../../database/OPERATIONS.md) | Repository pool-restart/full-state tests, API execution interruption/recovery, [export validation tests](../../00_backend/tests/test_migration.py), operator dry-run/rollback/retry/collision/history and reconnect rehearsal |

### Findings resolved before completion

Two frontend authentication edge cases were found and reproduced with failing
tests during final review:

1. A campaign 401 cleared content but also rediscovered workspaces. Discovery could
   restore selection while navigation was pending. Both discovery and campaign
   session-expiry paths now abort discovery, clear selection/content, and stop
   fetching until navigation completes. The regression deliberately keeps router
   navigation pending and makes discovery capable of succeeding.
2. Middleware redirected sessionless API fetches to an HTML login page. It now
   returns JSON 401 for API paths while retaining redirects for page navigation.
   A proxy regression and real standalone-server browser requests verify this.

The R4 acceptance scenarios explicitly describe JSON errors at the same-origin API
boundary; R5 already required cleared content and no restoration after expiry.
After these fixes, `bun run test` passed 33 tests, `bun run lint` and `bun run build`
passed, and `bun run test:browser` passed all 24 desktop/mobile checks. The backend
was unchanged, so its recorded 63 unit + 42 PostgreSQL results remain the backend
evidence rather than claiming another run. Final documentation links, checklist
completion, and `git diff --check` were also checked.

### Completion boundary

No unresolved in-scope implementation or validation item remains. Spec 001 and its
index entry are Implemented; all T01–T15 items (including T03a/T03b) are checked.
Live Firebase/Cloud SQL credentials and networking, source inventory/quiescence,
production backup/import, and deployed browser smoke checks remain rollout work.
The automated restart evidence uses a new connection pool. Browser fixtures do not
claim an authenticated browser-to-database end-to-end run. These limits are retained
in the evidence and runbook; no deployment, live migration, or publication occurred.
