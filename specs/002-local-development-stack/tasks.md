# 002: Local development stack tasks

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] T01: Resolve local service names, ports, database identities,
  environment-file layout, Firebase project, and ADC strategy (002-R1–R4).
  Decisions: `compose.local.yaml`; services `postgres`, `api`, `frontend`; host
  ports 5433 (loopback), 8080, and 3000; root ignored `.env`; persistent local
  volume; separate migration/runtime/operator logins; current Firebase project
  `marketing-generator-51cc0`; read-only ADC mount with local non-root UID/GID
  compatibility and preserved frontend cache writes.
- [x] T02: Add a separate persistent PostgreSQL Compose service and explicit
  first-run database role, migration, and grant workflow (002-R2, 002-R3).
  Evidence (2026-09-26): `docker compose -p campaign-local-t02-check
  --env-file .env.example -f compose.local.yaml run --rm migrate` applied
  migrations 001–004 and grants to a fresh isolated PostgreSQL 16 volume. A
  second run detected schema version 4 and reapplied grants. Role checks showed
  all three app roles are non-superuser and lack CREATEDB/CREATEROLE; runtime
  campaign SELECT and denied user UPDATE, plus operator membership INSERT, were
  verified. The isolated validation volume was removed.
- [x] T03: Add Compose API/frontend services with correct network URLs, build
  arguments, Firebase credential mounts, and deterministic runner configuration
  (002-R1, 002-R4, 002-R5). Evidence (2026-09-26): Compose built the backend and
  frontend images; an isolated stack started with all three health checks
  passing after migrations. Both app containers could read the read-only ADC
  mount as UID 501; the frontend UID could write `/app/.next`. The temporary
  stack/volume were removed. Live Firebase calls and deterministic campaign
  behavior were followed up under T05.
- [x] T04: Document Firebase setup, ADC access, workspace/member provisioning,
  health checks, lifecycle, reset, and troubleshooting (002-R1, 002-R4–R6).
  Evidence (2026-09-26): `LOCAL_DEVELOPMENT.md` now includes a Compose first-run
  walkthrough, Firebase project/provider/origin and ADC setup, exact operator
  commands using the local operator role, health endpoints and limits, logs,
  stop/start/down behavior, a reset scoped to the local named volume, and
  troubleshooting for configuration, ADC, database, Firebase, membership, and
  port failures. Command names/arguments were checked against Compose and
  `campaign.manage`; live sign-in remained environment-dependent and was tracked
  under T07.
- [x] T05: Validate a clean first run, database persistence/isolation, least
  privilege, deterministic behavior, and credential handling; record exact
  evidence and remaining cloud-dependent checks (002-R1–R6). Evidence
  (2026-09-26): A fresh uniquely named Compose project initialized the local
  PostgreSQL volume, applied migrations 001–004 and grants, built both app
  images, and reached healthy PostgreSQL/API/frontend states. Compose rejected
  missing runtime-password and Firebase App ID values with actionable messages.
  A campaign row remained after restarting API/frontend; a live API-container
  query returned `campaign_runtime` and one campaign. The disposable test
  PostgreSQL remained healthy throughout and after removal of only the T05
  Compose project/volume. Role and grant checks from T02 passed; all 42
  PostgreSQL integration tests, 63 non-integration backend tests, and 33
  frontend tests passed.
  Both ADC mounts were readable and had Docker `RW=false`; neither image
  contained the ADC path/file, and the frontend cache was writable. At the time
  of T05 validation, interactive Firebase sign-in, actual Firebase Admin API
  calls, and browser membership behavior remained environment-dependent; T07
  subsequently completed those checks.
- [x] T06: Link the runbook and index the spec; update status only when all
  requirements have evidence (002-R1–R8). Evidence (2026-09-26): The README now
  links directly to the Compose quick start and to the complete environment
  reference; the spec is indexed in specs/README.md with a quick-start link.
  Final spec status was set to Implemented after T07 acceptance and validation.
- [x] T07: Complete live Firebase Admin, sign-in, workspace membership,
  origin-aware session-cookie, and Google account-selection checks against the
  configured local project (002-R4, 002-R5, 002-R7, 002-R8).
  Prerequisites: valid root `.env`; Compose stack initialized and healthy;
  authorized ADC readable in the API and frontend containers; Google sign-in
  enabled and `localhost` authorized in Firebase project
  `marketing-generator-51cc0`; and two existing Firebase users (one provisioned
  with an active workspace role, one without active membership). Verify browser
  sign-in/session creation and server-side Firebase Admin verification through
  the frontend and API; verify the provisioned member can access the workspace
  and perform role-permitted deterministic campaign operations; verify the
  unprovisioned user sees the no-workspace state and cannot read campaign data.
  Verify that the session cookie is accepted over the local HTTP origin and has
  the Secure attribute under HTTPS; verify logout clears it with matching
  attributes. Verify a second Google account can be selected after app logout
  while the browser retains its Google session. Record pass/fail and
  non-sensitive evidence for each scenario without saving session cookies,
  tokens, ADC contents, or user secrets.
  Evidence (2026-09-26): Created the ignored root `.env` with mode 0600,
  unique database passwords, current project settings, and the existing ADC
  path; the isolated local stack is healthy. Aligned the local ADC quota project
  to `marketing-generator-51cc0`; a read-only Firebase Admin lookup verified
  the supplied account is present and enabled. Created the local workspace
  `t07-local-firebase-verification` and assigned that account active
  `approver` membership through the operator CLI. Firebase Admin verified the
  second supplied UID is present and enabled; a read-only query through the
  runtime database connection confirmed it has zero active workspace
  memberships. The in-app browser tool was unavailable, but the user exercised
  sign-in in their browser: `/api/auth/session` returned 200 with `Set-Cookie`,
  the browser did not retain the cookie, and `/api/auth/me` returned 401. This
  exposed that cookies used `NODE_ENV` to set `Secure`, even though the local
  Compose origin is HTTP and the production image sets `NODE_ENV=production`.
  002-R7 now specifies origin-aware session and logout cookie attributes. The
  user subsequently confirmed sign-in and app logout work with the provisioned
  member account. After logout, Google reused the prior account instead of
  offering a different one, so 002-R8 adds account selection on each Google
  sign-in. Its provider configuration test passes, and the updated frontend
  image is deployed and healthy. The user confirmed live account switching,
  role-permitted deterministic campaign operations, and no-workspace/data-denial
  behavior for the unprovisioned account. Added route-level tests that inspect
  serialized cookie headers for HTTPS and HTTP session creation and logout; all
  four cases passed. Full frontend validation passed: 42 tests, lint, and
  production build. No account was created or deleted by the CLI.
- [x] T08: Harden and verify Git ignore coverage for local environment files and
  credential artifacts (002-R4). Evidence (2026-09-26): `git check-ignore` confirms
  root/nested `.env` variants, ADC and common credential/private-key filenames
  are ignored; `.env.example` templates remain eligible for tracking. The
  tracked file-name audit found no committed environment files or credential
  artifacts, and a scan found no private-key/ADC token markers in tracked text.
  The example database passwords and ADC path are placeholders; Firebase web
  configuration is intentionally public.
