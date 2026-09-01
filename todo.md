# Security Remediation TODO

## Critical

- [ ] Replace the cosmetic login flow with real authentication.
  - Use a mature identity provider and validate identity server-side.
  - Store sessions in `HttpOnly`, `Secure`, appropriately `SameSite` cookies.
  - Add session expiration, logout, account recovery, and protected-route middleware.
  - Do not accept or store passwords directly unless a mature authentication service handles them.

- [ ] Require authentication and authorization for every campaign API operation.
  - Protect campaign creation, listing, retrieval, execution, and approval endpoints.
  - Associate every campaign with a tenant/workspace and verify ownership on each request.
  - Define and enforce viewer, editor, runner, and approver roles in the backend.
  - Never rely solely on hidden or disabled frontend controls for authorization.

- [ ] Make approval identities trustworthy.
  - Derive the approval actor from the authenticated server-side identity.
  - Require an approver role for approval and rejection operations.
  - Store immutable, timestamped audit events.
  - Consider step-up authentication before approving publication.

## High Priority

- [ ] Restrict Cloud Run access and service-account permissions.
  - Remove anonymous access from the backend.
  - Permit backend invocation only from the frontend service identity or authenticated gateway.
  - Replace the Firebase Admin service account with a dedicated least-privilege account.
  - Review and minimize every IAM permission assigned to both services.

- [ ] Add rate limits, quotas, and AI workload controls.
  - Apply per-user and per-workspace request limits.
  - Limit campaign runs and concurrent runs per campaign.
  - Put expensive AI work behind a bounded queue where appropriate.
  - Set model input, output, token, timeout, and retry limits.
  - Configure global spend caps, usage monitoring, and billing alerts.

- [ ] Add strict input and output limits.
  - Set maximum lengths for goals, audiences, comments, constraints, and generated text.
  - Set maximum list sizes and metadata depth, key count, and serialized size.
  - Set a maximum campaign budget and validate supported currencies.
  - Allow only supported channel identifiers.
  - Enforce request-body size limits before reading the full body.
  - Limit model response and stored campaign-state sizes.

- [ ] Harden AI workflows against prompt injection and unsafe output.
  - Treat briefs, metadata, and previous model output as untrusted data.
  - Clearly delimit untrusted content in prompts and reinforce instruction hierarchy.
  - Validate the semantics of generated channels, activities, claims, links, and actions.
  - Moderate generated campaign content where appropriate.
  - Preserve mandatory human review before external side effects.
  - Do not expose broad credentials or unrestricted tools to agents.
  - Add prompt-injection and adversarial-input tests.

- [ ] Harden or remove the standalone development agent service.
  - Remove wildcard CORS and allow only exact trusted production origins.
  - Disable the ADK web interface in production.
  - Authenticate and authorize all agent endpoints.
  - Ensure local session databases are not committed or copied into images.

## Medium Priority

- [ ] Prevent duplicate and conflicting campaign transitions.
  - Replace the in-memory repository with durable production storage.
  - Add optimistic concurrency using the campaign version.
  - Make phase transitions and approval decisions atomic.
  - Add per-campaign execution locks and idempotency keys.
  - Return conflict responses for stale or duplicate operations.

- [ ] Stop exposing internal exception details.
  - Return stable public error codes and generic user-facing messages.
  - Keep stack traces and provider details only in access-controlled logs.
  - Redact credentials, prompts, campaign data, and personal data from logs.
  - Do not store raw internal exception messages in API-visible campaign state.

- [ ] Add browser and API request hardening.
  - Configure a restrictive Content Security Policy.
  - Add HSTS, `X-Content-Type-Options`, `Referrer-Policy`, and `Permissions-Policy`.
  - Prevent framing with CSP `frame-ancestors` or an equivalent header.
  - Add Origin validation and CSRF protection when cookie authentication is enabled.
  - Restrict accepted HTTP methods and content types.

- [ ] Establish AI and campaign data-governance controls.
  - Document which campaign fields and intermediate outputs are sent to model providers.
  - Classify and redact confidential or personal information before model calls.
  - Configure approved model regions, retention settings, and access policies.
  - Encrypt durable data in transit and at rest.
  - Define retention, export, and deletion policies.
  - Avoid logging model prompts and responses by default.

## Supply Chain and Operations

- [ ] Run automated dependency vulnerability scans for Python and JavaScript lockfiles in CI.
- [ ] Lock Python dependencies to reproducible, reviewed versions.
- [ ] Pin container base images by digest and scan final images.
- [ ] Generate an SBOM and enable build provenance and image signing.
- [ ] Run secret scanning in local hooks and CI.
- [ ] Ensure `.env` files, build output, session databases, and credentials are excluded from Git and container build contexts.
- [ ] Deploy immutable image digests; do not rely on the mutable `latest` tag.
- [ ] Keep production API documentation private or disable it when unnecessary.
- [ ] Add centralized security logging, alerting, and audit-log retention.

## Security Verification

- [ ] Test that anonymous users cannot access the dashboard or campaign APIs.
- [ ] Test cross-tenant campaign access and identifier enumeration.
- [ ] Test role restrictions for run, approve, and reject operations.
- [ ] Test forged approval identities and replayed approval requests.
- [ ] Test simultaneous and duplicate phase-run requests.
- [ ] Test oversized bodies, strings, lists, metadata, and model responses.
- [ ] Test CSRF defenses after cookie authentication is introduced.
- [ ] Test CORS and production security headers.
- [ ] Test prompt injection, malicious campaign content, and unsafe generated actions.
- [ ] Perform a dependency audit and an authenticated penetration test before production launch.

