# Marketing Campaign Dashboard

A Next.js dashboard for creating campaign briefs and guiding them through the
planning, development, execution approval, and monitoring lifecycle.

## Local development

```bash
bun install
cp .env.example .env.local
bun run dev
```

Set the public Firebase values in `.env.local` for your project and configure
Firebase Admin ADC for the Next.js server. Use the same project as the backend.
Set `APP_ORIGIN` to the frontend origin used for session/logout requests.

The backend defaults to `http://localhost:8080`. The browser calls same-origin
Next.js route handlers, which proxy requests to the backend and avoid CORS.

## Dashboard workflow

1. Sign in with your Firebase account and select a workspace. An operator must
   first assign your UID a membership; a sole workspace is selected automatically.
2. Create a campaign brief (editor or higher).
3. Run the agent workflow (runner or higher) through planning, development, and execution prep.
4. Approve or reject (approver) the execution package.
5. Continue an approved campaign into monitoring.

The runner badge shows whether the backend is using deterministic or ADK mode.

## Workspace validation

Run `bun run test` for deterministic dashboard interaction, API client, and proxy
route tests, then `bun run lint` and `bun run build`. Tests mock the session and
HTTP boundaries and need no Firebase credentials or running backend.

The dashboard auto-selects a sole workspace and requires selection when several
are available. Selection is held only in memory. Switching clears drafts and
ignores old requests; logout clears access immediately. Controls follow the
workspace role, while the backend enforces membership and permissions. See
[spec 001](../specs/001-workspace-authorization/tasks.md) for validation evidence
and browser smoke coverage.

### Browser smoke checks

After configuring the public Firebase client settings used by the build (no live
sign-in is required), run these commands sequentially from `00_frontend/`:

```sh
bun install --frozen-lockfile
bunx playwright install chromium --only-shell
bun run build
bun run test:browser
```

The suite starts its own standalone production server on `127.0.0.1:3100` and
closes it when finished. Keep that port free and do not rebuild while tests run.
Desktop and mobile Chromium checks use synthetic sessions and intercepted API
fixtures; production authentication is unchanged. They cover workspace selection,
roles, switching, approval flow, membership removal, session expiry, and logout.
They complement the real PostgreSQL backend integration suite and do not claim
live Firebase or deployment validation. Screenshots and failure traces are saved
in ignored `test-results/`. See [T13 evidence](../specs/001-workspace-authorization/validation.md).
