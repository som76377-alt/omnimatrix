# Omnitrix quality guardrails and reasoning protocol

## What is enforced

Omnitrix now has a versioned quality contract in `core/policy/quality.py`, composed into model
instructions and checked before model requests. It requires task completion over generic advice,
anti-slop output, evidence calibration, deliberate reasoning on complex tasks, a tool-and-test
verification loop, and precise reporting of what actually happened.

The quality contract complements rather than replaces `core/policy/truthfulness.py`. The latter
focuses on honesty and capability claims; the quality contract focuses on doing the requested work
well and checking it.

## High-reasoning route

The configured OpenRouter Nemotron 3 Super profile requests `reasoning.effort=high` and excludes
reasoning-token content from the user-visible response. The model is configured through OpenRouter;
its real provider-reported model identifier is captured when the API supplies one. High effort is a
request setting, not a guarantee of correctness and not training/fine-tuning of model weights.

The agent router uses the reasoning specialist for general reasoning, specialist instructions for
domain work, and the critic on complex requests under the existing `complex_only` policy. This is
deliberate: adding a second live call to every trivial message would spend free-route quota and add
latency without proportionate value. The critic's result is only applied if it satisfies the
existing response schema.

## Model identity in Studio

After a completed turn, the API returns an execution trace containing only model-call metadata:
stage, role, provider, configured model, provider-reported model identifier when available, identity
source, and latency. It does not return prompts, user content, raw model reasoning, or secrets.
Studio displays the model from the trace under the Omnitrix Core name and in the completed reply's
source line. When the provider does not report an identifier, the UI explicitly marks the configured
ID as the source instead of pretending it is provider-verified.

No model is allowed to expose private chain-of-thought. The UI shows which model and specialist
participated, not the model's private reasoning text.

## Verification and limits

The automated tests check policy injection, configuration of reasoning effort, response metadata,
and UI/API trace propagation. The live free-route smoke benchmark is separately opt-in through
GitHub Actions. Passing offline tests proves code contracts only; a live API request and production
deployment must be separately observed before they can be reported as working.
