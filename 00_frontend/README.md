# Marketing Campaign Dashboard

A Next.js dashboard for creating campaign briefs and guiding them through the
planning, development, execution approval, and monitoring lifecycle.

## Local development

```bash
bun install
cp .env.example .env.local
bun run dev
```

The backend defaults to `http://localhost:8080`. The browser calls same-origin
Next.js route handlers, which proxy requests to the backend and avoid CORS.

## Dashboard workflow

1. Create a campaign brief.
2. Run the agent workflow through planning, development, and execution prep.
3. Approve or reject the execution package.
4. Continue an approved campaign into monitoring.

The runner badge shows whether the backend is using deterministic or ADK mode.
