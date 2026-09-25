# 000: Campaign lifecycle

Status: Historical baseline (2026-09-24)

## Scope and sources

Observed behavior in `00_backend/campaign/orchestrator.py`, `repository.py`,
`auth.py`, and `00_backend/main.py`. This describes the implementation observed on 2026-09-24,
including limitations, rather than a production readiness target.

Storage, workspace authorization, concurrency, and approval attribution are
superseded by [001: Workspace authorization](../001-workspace-authorization/spec.md).
The limitations and evidence below are historical, not current API behavior.

## Requirements and acceptance scenarios

### 000-R1: Ordered phases

Phases run in order: planning, development, execution, monitoring.

- Given a new campaign, when development is requested first, then the orchestrator
  raises InvalidTransitionError; the API maps this error to HTTP 409.

### 000-R2: Approval gate

- Given a new campaign, when run-until-blocked executes, then planning and
  development produce outputs and execution pauses in awaiting_approval.
- Given execution awaiting approval, when approved and run again, then monitoring
  completes and the campaign becomes completed with an approval record.
- Given execution awaiting approval, when rejected, then execution and campaign
  become failed and the rejection comment is retained.

### 000-R3: Verified identity

- Given a campaign API request without a session, when authentication runs, then
  it rejects the request with HTTP 401.
- Given a valid Firebase session, when an approval is recorded through the API,
  then the actor comes from the verified user's email, name, or UID, in that order.

### 000-R4: Honest placeholder output

- Given deterministic execution, when activities are generated, then they describe
  prepared publication work without publishing externally.
- Given deterministic monitoring, when KPIs are produced, then requested metrics
  have null values and the output explains that live analytics are unavailable.

## Known limitations

- The repository stores campaigns in memory and loses them on restart.
- Authenticated requests are not scoped by workspace or role.
- Version increments are not optimistic concurrency checks; repository locks do
  not make a whole asynchronous phase run atomic.
- A failed or rejected phase can be retried as the next incomplete phase.
- Existing unit tests cover only part of this baseline; API status mapping,
  approval actor wiring, placeholder semantics, and retry paths need focused coverage.

## Evidence map

| Requirement | Existing evidence | Coverage |
| --- | --- | --- |
| 000-R1 | `tests/test_orchestrator.py::CampaignOrchestratorTests::test_phase_order_is_enforced` | Orchestrator only |
| 000-R2 | `tests/test_orchestrator.py::CampaignOrchestratorTests::test_full_lifecycle_stops_for_approval_then_completes` and `test_rejection_fails_execution` | Happy path and rejection |
| 000-R3 | `tests/test_auth.py::test_require_user_rejects_missing_session` and `test_require_user_uses_verified_firebase_claims` | Auth helper only; no API wiring proof |
| 000-R4 | ExecutionRunner and MonitoringRunner source inspection | Automated assertions missing |

Test paths above are relative to `00_backend/`. Execution results are recorded below.

Validation on 2026-09-24, from `00_backend/`:

- `.venv/bin/python -m unittest discover -s tests -p test_orchestrator.py`:
  passed all 3 lifecycle tests (000-R1 and 000-R2, within the coverage limits above).
- `.venv/bin/python -m pytest tests/test_orchestrator.py tests/test_auth.py`:
  could not run because pytest is not installed in the local virtual environment.
  Authentication tests were not executed during this setup.
