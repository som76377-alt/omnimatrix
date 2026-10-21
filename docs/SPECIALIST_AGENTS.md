# Specialist agents and model candidates

**Snapshot:** 18 October 2026  
**Status:** Role routing, a Google adapter baseline, and an opt-in OpenRouter adapter are implemented on the feature branch. The free models are configured but have not yet passed Omnitrix's own live benchmarks. Anthropic/OpenAI adapters and cross-provider premium routing remain future work.

## Design rule

Omnitrix remains the authority for the user's objective, permissions, budgets, task/run state, and final report. Specialist agents are replaceable role policies. A role is not a separate AI model merely because it has a name. It becomes a separately powered specialist only when the configuration points it to a registered, enabled adapter with suitable capabilities and an explicitly approved cost class.

The default live configuration retains `omnitrix-primary` (`gemini-3.8-flash`) as the baseline and now also registers `reasoning-nemotron-super-free` (`nvidia/nemotron-3-super-120b-a12b:free`) through OpenRouter. The Reasoning role prefers that model when the OpenRouter key is configured, the adapter is available, and the runtime budget allows it; otherwise it falls back to an eligible configured model. This is a zero-price endpoint, not a guarantee of unlimited capacity, privacy, or uptime. The separate `config/mobile.models.openrouter-free.example.json` profile remains available for trying the other free candidates. The demo provider remains simulated and does not run the live specialist pipeline.

## Initial role design

| Role ID | Responsibility | Initial candidate to test | Required evidence |
|---|---|---|---|
| `intent_engineer` | Translate a short or ambiguous user message into a concise, structured task brief for the orchestrator: intent, deliverable, constraints, assumptions, steps, acceptance criteria, domain, complexity | Gemini 3.8 Flash for the low-latency baseline; compare Gemini 4 Argon and a smaller routing model such as Claude Haiku 5.5 or GPT-6 Luna if configured | Does not lose constraints, invent requirements, overcomplicate simple prompts, or ask unnecessary questions |
| `reasoning` | General analysis, explanations, decisions, and planning | **Initial configured choice: NVIDIA Nemotron 3 Super 120B A12B via OpenRouter's `:free` route**; higher-end challengers remain Gemini 4 Argon, GPT-6 Astra, and Claude Fable 5.1 | Hard reasoning set, calibration, adversarial consistency, useful latency |
| `coding` | Repository-aware implementation, debugging, test design, and refactoring | Claude Opus 5.5, GPT-6 Astra, Gemini 4 Argon; use North Mini Code free as the first no-cost candidate | Tests that actually pass, regression rate, patch quality, tool-use reliability |
| `subject_solver` | Maths, physics, chemistry, biology, and other technical/academic reasoning | Gemini 4 Argon, GPT-6 Astra, Claude Fable 5.1; first no-cost candidate is Nemotron 3 Super, with Nemotron 3 Ultra as a disabled challenger pending reliability tests | Verified solutions, correct derivations, dimensional/unit checks, edge cases, source accuracy |
| `research` | Evidence gathering, source comparison, current facts, documentation research, and citation discipline | Nemotron 3 Super or the configured Google model as a baseline; premium models remain candidates until adapters are added | Real source retrieval, freshness, source-claim match, independent corroboration, citation accuracy |
| `computation` | Exact arithmetic, expression evaluation, numeric cross-checks, and unit calculations | Nemotron 3 Super as the first available candidate; use the registered calculator tool where appropriate | Deterministic calculation checks, correct units, boundary cases, and truthful reporting when a tool cannot solve the requested expression |
| `critic` | Try to falsify a draft, identify meaningful errors, and propose a corrected answer when needed | A different upstream model and ideally a different provider; benchmark Gemini 4 Argon, GPT-6 Astra, Claude Fable 5.1, and the free candidates against planted-error tests | Finds planted errors, avoids false alarms, preserves correct answers, distinguishes factual verification from reasoning |

These are **candidates for head-to-head evaluation, not a claim that one model always wins**. Premium names in `config/agents.json` are preferences/aliases only until the relevant provider adapter and model profile are configured. The free OpenRouter candidates are configured in the example profile, and Nemotron 3 Super is additionally registered in the main model profile for the Reasoning role. This does not create credentials or prove that the upstream endpoint is currently available.

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
- **GPT-6 Astra** is OpenAI's flagship candidate for the hardest reasoning/coding/science tasks. **GPT-6.1 Sol** is the lower-cost speed/intelligence balance. The current standard short-context list price is $10/M input and $50/M output for Astra; $2/M input and $10/M output for Sol before processing/context-specific variations. Sources: [OpenAI model catalogue](https://developers.openai.com/api/docs/models), [API pricing](https://developers.openai.com/api/docs/pricing).
- **Gemini 3.8 Flash**, the configured current model, is described by Google as its most intelligent Flash model for long-horizon software engineering and agentic workflows. Google's pricing page lists free-tier input/output for eligible access, with limits and data-use conditions. Free-tier access is quota-limited, not a promise of unlimited uptime or capacity. Source: [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Provider descriptions and list prices are not a benchmark. Model IDs, rate limits, and prices can change; verify them before configuring a provider. The user's existing zero-cost default remains authoritative.

## Execution behavior in version 1

Eight role policies are now registered: intent engineer, orchestrator, reasoning, coding, subject solver, research, computation, and critic. These are configurable roles; they do not imply seven separate model weights or seven independent providers.

1. **Route** with deterministic, testable rules: explicit numeric expression requests to computation; source-retrieval requests to research; subject-science requests to the subject solver; software/repository work to coding; general requests to reasoning. Hybrid work attaches research or coding as a supporting instruction when it adds a distinct lens.
The provider adapter currently exposes registered model tools; it does **not** yet provide a native web-search or general Python/SymPy/SciPy tool. Therefore:
- The `research` role can enforce research methodology and source honesty, but it cannot retrieve live sources unless a real search/retrieval tool is added and authorized.
- The `computation` role can request use of the existing calculator tool if it is available and authorized. That calculator has limited expression support; symbolic algebra, advanced numerical methods, and dimensional-analysis tooling are follow-up work.
- These two additions complete the role scaffolding, not the later per-agent training/prompt refinement, tool integrations, and benchmark work.

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

- `core/agents/registry.py` — validates configurable specialist definitions, including the dedicated orchestrator role.
- `core/policy/agent_boundaries.py` — assigns narrow role/tool allowlists, support handoff contracts and the coordinator's output constraints.
- `core/agents/router.py` — routes roles and composes instructions.
- `core/models/providers/openrouter.py` — opt-in Chat Completions adapter with tool-call normalization and no automatic retries.
- `config/agents.json` — role definitions, preferences, intent and critic policies.
- `core/orchestrator/omnitrix.py` — bounded no-tool orchestrator, intent, support-specialist and critic stages under the existing budget/journal contracts; validates coordinator work packages before dispatch.
- `tests/test_agents.py` and `tests/test_agent_pipeline.py` — deterministic routing/schema and scripted-call regression tests.

Current limitation: **the provider registry only supports Google and the offline demo implementation.** Anthropic/OpenAI adapters, independent model access, live model benchmarking, tool-based symbolic/numeric calculation, and a separate task-decomposition worker are follow-up increments—not done merely by adding this role configuration.


## Reasoning model configuration update

The first concrete Reasoning model assignment is `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter, selected as the zero-price starting point rather than a claim that it beats paid frontier models. The role's preference list places it first. `config/mobile.models.json` registers it separately from the Gemini baseline; actual routing requires `OPENROUTER_API_KEY`, an available route, and a runtime budget mode that permits the free model. When unavailable, Omnitrix can fall back to the eligible configured baseline; status must not represent the fallback as Nemotron. The OpenRouter free route has privacy/availability caveats: do not send confidential, personal, or sensitive data. No key is stored in the repository.
