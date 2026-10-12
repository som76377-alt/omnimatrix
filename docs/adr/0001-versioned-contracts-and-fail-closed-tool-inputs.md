# ADR 0001: Versioned contracts and fail-closed tool input validation

- **Status:** Accepted for the Phase 1 implementation increment
- **Date:** 2026-10-12
- **Decision owners:** Omnitrix project owner and implementation maintainer

## Context

Omnitrix has a working planning/task foundation, but worker handoffs, event envelopes, normalized failures, and resource budgets need stable provider-neutral contracts. Tool definitions already publish JSON-Schema-like argument schemas, yet the executor previously passed arguments directly to tool code without validating them. Plan fingerprints previously covered task labels and dependency edges only, so material changes to intended scope or policy were not fingerprinted.

## Decisions

1. Add versioned, provider-neutral WorkerRequest, WorkerResult, RunEvent, error codes, and budget primitives in core/contracts.py.
2. Treat worker context as explicitly trusted or untrusted data. A structured success/failure status is authoritative over persuasive free text.
3. Bind plan approval fingerprints to the existing task graph and a declarative execution context: tool scopes, targets, resources, verification criteria, policy version, spend mode, risk tier, and external-data-egress intent.
4. Display that context in plan previews so reviewers can inspect what the fingerprint binds.
5. Validate tool arguments against a documented dependency-free JSON Schema subset before invoking a tool. Reject malformed/unsupported schemas and invalid arguments without running the tool.
6. Preserve the zero-cost default in the budget primitive; unknown cost classes are rejected in strict zero-cost mode.

## Consequences and limitations

- Existing PlannedTask construction remains compatible because the plan context has a safe default.
- The schema validator intentionally supports a subset, not the entire JSON Schema standard. Unsupported keywords fail closed and must be added deliberately with tests.
- A plan fingerprint proves that a supplied record matches a plan; it does not prove that a human actually approved it.
- PlanExecutionContext currently records approval-sensitive intent but does not yet independently enforce every declared target/resource/scope during execution.
- BudgetGuard is a tested primitive in this increment, but provider call sites are not yet wired to it. The Phase 1 acceptance gate remains in progress until provider cost classification and call-boundary enforcement are implemented and tested.
- Durable run state, crash recovery, retries/idempotency, and a persistent event journal remain later phases.

## Verification

The acceptance checks for this increment are the repository CI workflow: Python compilation, demo config JSON validation, full unittest discovery, and an offline CLI smoke test. Do not mark the full Phase 1 gate complete solely because these structural contracts exist.
