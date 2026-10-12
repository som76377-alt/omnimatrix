# Architecture: current implementation

This document describes what is present in the repository today, not the full target architecture. The implementation is an early Python CLI prototype; the roadmap separates current foundations from planned capabilities.

## Main path

1. `interfaces/cli/main.py` parses the required `--config` argument, builds `Omnitrix` from that model configuration, creates a `ChatApplication` and `Conversation`, then starts the interactive loop.
2. `core/application/chat.py` provides the chat application boundary.
3. `core/orchestrator/` contains orchestration, analysis, plan construction/validation, and task-level behavior.
4. `core/models/` defines model-facing types, provider registration/builders, and configuration loading.
5. `core/tools/` defines tool contracts, permissions, registry, and execution. Tool implementations are registered capabilities, not unrestricted general-purpose computer control.
6. `tests/` contains the regression suite for these contracts and their interactions.

## Model providers

Provider-specific behavior is kept behind the model abstraction. The checked-in offline profile, `config/demo.models.json`, selects the explicitly named `demo` provider. It generates a **simulated response** and does not perform real model inference or external work. This is the preferred profile for a zero-cost smoke test.

The Gemini adapter reads `GEMINI_API_KEY` from the process environment. Credentials must never be committed. Before depending on live inference, verify that the selected model identifier and provider API configuration are currently supported. Do not silently switch a failed live provider to the demo provider: simulated output is not a substitute for live inference.

## Planning and execution

The current foundations include structured plans, validation, dependency-aware task ordering, task lifecycle/observability, and propagation of completed dependency results to downstream tasks as untrusted context. Model-produced plans and tool-derived text must be treated as data to validate, not as authority to bypass policy.

The plan-approval fingerprint is based on the fields present in the current plan model (task identifiers, descriptions, and sorted dependencies). It can detect a changed plan relative to a fingerprint, but a fingerprint alone cannot prove that a human saw and approved the plan. The caller/application must obtain explicit consent, and execution paths must not treat a model's claim of approval as consent. As plan schemas evolve, approval must cover every field that can affect scope, side effects, cost, target resources, or verification.

## State and failure boundaries

Conversation and task state are currently process-local; durable SQLite-backed history, crash recovery, and robust pause/resume are future work. Do not describe task execution as crash-resumable until persistence and fault-injection tests demonstrate it.

A failed task should not be reported as successful. Verification must be distinct from the worker's own assertion that it completed. Retry rules, idempotency, external side-effect reconciliation, artifact preservation, and restart integrity require explicit implementation and tests before broad automation is safe.

## Current non-goals / not yet implemented

The repository should not yet be represented as a finished Android app, live streamed desktop, unrestricted browser/terminal operator, multimodal creative suite, or fully autonomous general agent. These are target capabilities to build in phases with their own quality gates. Keep provider usage explicit and maintain a working offline demo path while iterating.
