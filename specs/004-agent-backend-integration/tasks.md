# 004: Tasks

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] Inspect existing integration and document scope, acceptance scenarios, and decisions (004-R1–R7).
- [x] Verify locked ADK provider/event/session interfaces; wire Settings into provider construction and test credential precedence/redaction (004-R1).
- [x] Retain four canonical factory mappings and deterministic default; test startup failure and health mode (004-R1, 004-R7).
- [x] Implement completed-upstream-only context and fresh attempt isolation; add retry/concurrency fixtures (004-R2).
- [x] Implement session cleanup on success, error, cancellation, and cleanup failure (004-R2, 004-R5).
- [x] Select only the expected synthesizer's final response; test every phase and malformed/missing/nested-invalid output (004-R3, 004-R5).
- [x] Strengthen recursive agent/backend schema compatibility and cross-validation fixtures (004-R3).
- [x] Align prompts with industry, constraints, completed planning, and text asset scope (004-R6).
- [x] Validate generated draft/prepared statuses and missing-data KPI rules without changing stored-record schemas (004-R6).
- [x] Exercise active API with fake-backed ADK adapters through approval, rejection/retry, durable readback, failure, authorization, and lock contention (004-R4, 004-R5, 004-R7).
- [x] Run focused/unit and disposable database checks; verify image imports without provider calls (004-R1–R7).
- [x] Update runtime configuration/operator documentation and record exact evidence, remaining gaps, and status in the spec/index (004-R1–R7).

All tasks completed 2026-10-03. See [final evidence and limitations](spec.md#evidence).
Optional live smoke and deployment were not performed.
