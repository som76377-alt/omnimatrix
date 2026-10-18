# Specialist agents and model candidates

**Snapshot:** 18 October 2026  
**Status:** Role layer implemented on the feature branch; multi-provider model adapters and empirical role benchmarks are not yet connected.

## Design rule

Omnitrix remains the authority for the user's objective, permissions, budgets, task/run state, and final report. Specialist agents are replaceable role policies. A role is not a separate AI model merely because it has a name. It becomes a separately powered specialist only when the configuration points it to a registered, enabled adapter with suitable capabilities and an explicitly approved cost class.

The default live configuration has a single Google model profile, `omnitrix-primary`, using `gemini-3.8-flash`. The specialist branch adds an opt-in OpenRouter adapter and the separate `config/mobile.models.openrouter-free.example.json` profile. That profile is deliberately **not** the default and is not activated by the existing mobile backend manifest. It adds free-endpoint candidates without changing the existing default. The demo provider remains simulated and does not run the live specialist pipeline.

## Initial role design

| Role ID | Responsibility | Initial candidate to test | Required evidence |
|---|---|---|---|
| `intent_engineer` | Translate a short or ambiguous user message into a concise, structured task brief for the orchestrator: intent, deliverable, constraints, assumptions, steps, acceptance criteria, domain, complexity | Keep the configured Gemini Flash model as the zero-additional-provider baseline; compare Gemini 4 Argon and a fast, low-cost model only after its API and cost class are configured | Does not lose constraints, invent requirements, overcomplicate simple prompts, or ask unnecessary questions |
| `reasoning` | General analysis, explanations, decisions, and planning | Gemini 4 Argon; compare GPT-6.1 Sol and Claude Opus 5.5 | Hard reasoning set, calibration, adversarial consistency, useful latency |
| `coding` | Repository-aware implementation, debugging, test design, and refactoring | Claude Opus 5.5 and Gemini 4 Argon; compare GPT-6.1 Sol | Tests that actually pass, regression rate, patch quality, tool-use reliability |
| `subject_solver` | Maths, physics, chemistry, biology, and other technical/academic reasoning | Gemini 4 Argon first for the evaluation set; compare GPT-6.1 Sol and Claude Opus 5.5 | Verified solutions, correct derivations, dimensional/unit checks, edge cases, source accuracy |
| `critic` | Try to falsify a draft, identify meaningful errors, and propose a corrected answer when needed | A different configured provider than the draft model, such as GPT-6.1 Sol reviewing a Google draft or Gemini reviewing an OpenAI/Anthropic draft | Finds planted errors, avoids false alarms, preserves correct answers, distinguishes factual verification from reasoning |

These are **candidates for head-to-head evaluation, not a claim that one model always wins**. Candidate names in `config/agents.json` are preferences/aliases only. They do not register providers, fetch model weights, create API credentials, or activate paid calls.

## Opt-in free candidates (snapshot: 18 October 2026)

The example profile exposes two free OpenRouter model IDs so the roles can be tried with a provider adapter without changing the default model file:

| Model | Suggested evaluation role | Current evidence and limitation |
|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | General reasoning; subject solving; intent brief | OpenRouter currently lists it as free, with tool-call support and a 262K context. Availability metrics on a provider page are a short time-window snapshot, not an uptime guarantee. |
| `cohere/north-mini-code:free` | Coding | OpenRouter describes it as a coding/agentic software-engineering model, with tool calling and a 256K context. Its code benchmark listings are only signals for test selection; repository-specific pass rates must decide if it is good enough. |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Experimental reasoning/science challenger | Model catalogues list a very large context and tool use, but its free route has shown uneven endpoint availability. It is present in the example profile **disabled by default** until a live smoke test and the benchmark suite establish adequate reliability. |

OpenRouter states its free plan is limited to **50 requests per day**; quotas and model routes can change. See [OpenRouter pricing](https://openrouter.ai/pricing), [Nemotron 3 Super free route](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free), [North Mini Code free route](https://openrouter.ai/cohere/north-mini-code:free), and [Nemotron 3 Ultra free route](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free).

**Privacy warning:** the current free Nemotron route states not to submit confidential or personal data and that requests may be logged and used to improve the service. Do not send private conversations, credentials, personal details, or sensitive repository content to that route. Review each upstream model/provider's current data terms, rate limits, availability, and region before use. Free does not mean private, reliable, or unlimited. The adapter never falls back silently; it only runs when the explicitly selected model profile and API credential are configured.

The premium candidates (Gemini 4 Argon, Claude Opus 5.5 and GPT-6.1 Sol) should remain in the evaluation matrix as **higher-end quality targets**, not default routes. They require separate API/provider implementations or credentials not added by the free profile. Their current published prices are meaningful: Gemini 4 Argon is not listed on Google's free API tier; Claude Opus 5.5 lists $4/M input and $20/M output; OpenAI prices vary with model/mode/context. Verify the providers' pages at selection time. Do not configure a paid role until its cost estimate, spend mode and maximum per-run budget are explicit.



## Why these candidates

- **Gemini 4 Argon** is officially described as Google's flagship reasoning model for complex software engineering, deep mathematical/scientific problem solving, and multi-step agents. It supports function calling and code execution. The official documentation says it is **not available on the free API tier**. Its introductory standard API rate is $2 per million input tokens and $10 per million output tokens through 30 November 2026, then $4/$20 from 1 December 2026. Sources: [model card](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon), [pricing](https://ai.google.dev/gemini-api/docs/pricing).
- **Claude Opus 5.5** is officially positioned for long-running agentic coding and knowledge work. The documented API price is $4 per million input tokens and $20 per million output tokens. Source: [Claude Opus 5.5 overview](https://platform.claude.com/docs/en/models/opus-5-5/overview).
- **GPT-6.1 Sol** is an additional candidate for reasoning, implementation, and review. OpenAI's published pricing lists a standard short-context rate of $2 input / $10 output per million tokens; pricing varies with processing mode and context. Source: [OpenAI API pricing](https://platform.openai.com/pricing).
- **Gemini 3.8 Flash**, the configured current model, is described by Google as its most intelligent Flash model for long-horizon software engineering and agentic workflows. Google's pricing page lists free-tier input/output for eligible access, with limits and data-use conditions. Free-tier access is quota-limited, not a promise of unlimited uptime or capacity. Source: [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Provider descriptions and list prices are not a benchmark. Model IDs, rate limits, and prices can change; verify them before configuring a provider. The user's existing zero-cost default remains authoritative.

## Execution behavior in version 1

1. **Route** with deterministic, testable rules: subject-science terms to the subject solver; software/repository terms or the existing coding capability to the coding role; otherwise general reasoning.
2. **Engineer intent adaptively.** Short ordinary questions skip the extra model call. Complex or vague work can trigger a no-tools preflight model call, returning a strict JSON brief. The brief is bounded, type/length-validated, marked as untrusted, and checked against the original user request by the main model. It is not allowed to override safety, permissions, costs, or the user’s explicit constraints.
3. **Use the lead specialist** through the existing registered model adapter and authorized-tool loop. Specialist prompts are instructions, not extra tool privileges.
4. **Critique complex work.** The critic receives the objective and draft but no tools. Omnitrix prefers a different provider when one is configured and approved. If no other provider is available, the critic may be the same underlying model and must not be represented as an independent second opinion.
5. **Validate outputs.** Invalid preflight JSON is ignored in non-journalled execution; malformed critic output leaves the original draft unchanged. In journalled execution, an uncertain provider-stage failure stops the task rather than hiding a dangling request boundary.
6. **Apply budgets.** Specialist calls pass through the same model-call budget guard. A model with a different cost class cannot silently replace the selected fallback; extra provider use must be explicitly approved in model metadata and remain inside the runtime's actual spend policy. No API keys are stored in this repository.

## Next: benchmark before making model assignments real

Use a small, locally repeatable evaluation set first, with the answers or acceptance criteria hidden from the model:

- **Reasoning:** multi-step logic, counterexamples, uncertainty calibration, and contradiction detection.
- **Coding:** real issues from this repository, hidden regression tests, patch size, test result, and whether the model falsely claims execution.
- **Subject solver:** multi-stage maths proofs, mechanics/electromagnetism, chemistry stoichiometry/equilibrium, unit conversions, and data interpretation. Score with symbolic/numeric checks and reference solutions wherever possible.
- **Critic:** inject known mistakes into correct drafts and leave other drafts correct; score true detections, missed errors, and false alarms separately.
- **Intent engineer:** short vague requests with relevant earlier constraints. Score constraint recall, unnecessary assumptions, excessive scope, unnecessary clarification, and whether the brief is actionable.

Track **accuracy, verifiable pass rate, latency, input/output tokens, cost per accepted result, failure rate, and fallback rate**. Do not compare scores from unrelated public leaderboards as if they were the same test. The role-to-model assignments should become defaults only after the tests show a real advantage.

## Implementation map

- `core/agents/registry.py` — validates configurable specialist definitions.
- `core/agents/router.py` — routes roles and composes instructions.
- `config/agents.json` — role definitions, preferences, intent and critic policies.
- `core/orchestrator/omnitrix.py` — bounded no-tool intent/critic stages under the existing budget and journal contracts.
- `tests/test_agents.py` and `tests/test_agent_pipeline.py` — deterministic routing/schema and scripted-call regression tests.

Current limitation: **the provider registry only supports Google and the offline demo implementation.** Anthropic/OpenAI adapters, independent model access, live model benchmarking, tool-based symbolic/numeric calculation, and a separate task-decomposition worker are follow-up increments—not done merely by adding this role configuration.
