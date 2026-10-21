# ECC and FreeLLMAPI integration

**Status:** implementation behind a review/deploy gate; a passing unit-test suite verifies local contracts, not provider availability or a successful Render deployment.

## What is installed

### Everything Claude Code (ECC)

Omnitrix installs a read-only checkout of upstream affaan-m/ECC at commit
90606c8315ee09cafc303515c5f33024db6b9882 into .tools/ecc when the Render
runtime is built, and when a Codespace is first created or rebuilt. The installer
checks the exact commit and checks that the upstream MIT license is present.

The runtime reads a short, explicitly selected subset of ECC Markdown skills
based on the active specialist role and objective. Selected references include
search-first, TDD workflow, verification loop, iterative retrieval, plan-orchestrate,
and security review. Content is length-bounded, code examples are removed, and a
policy wrapper identifies the content as advisory reference data. Omnitrix never
installs or executes ECC hooks, third-party plugins, setup commands, or scripts.
This is deliberate: ECC contributes useful workflow knowledge without replacing
Omnitrix's own coordinator, permissions, budget checks, Cline integration, and run
verification.

Omnitrix-native workflow contracts still apply when the ECC checkout is absent.
The default six-model profile and ordinary Codespaces workflows do not require
the gateway to work.

### FreeLLMAPI

The Render build uses upstream tashfeenahmed/freellmapi source pinned to commit
19eb7e1c3bd5e7421ee72c3878a099f511ea4275. The server is an optional
Node sidecar bound to 127.0.0.1:3001; it is not exposed as a public Render
service or public port. Omnitrix talks to it through the OpenAI-compatible
/v1/chat/completions endpoint using a separately generated FREELLMAPI_API_KEY.

The startup supervisor builds FreeLLMAPI's declarative provider-key configuration
in memory from credentials already configured in the hosting secret store. It
does not write provider keys to Git, command output, or supervisor logs. The
gateway encryption key and unified API credential are stored as Render
environment variables, not checked-in source.

## Cost and routing guardrails

FreeLLMAPI's auto:balanced strategy normally ranks the enabled model pool.
Omnitrix must not use that broad pool with unknown paid models. During startup,
the supervisor:
1. disables every gateway catalog model and fallback-chain entry;
2. enables only the exact model/key pairs present in Omnitrix's six configured
   slots and eligible for the owner's confirmed free quota;
3. writes the stable gateway API key to the gateway database;
4. verifies that no enabled model lies outside the allowlist; and
5. starts the Omnitrix server with the optional seven-entry model profile only
   after the gateway and allowlist checks succeed.

Groq routes are not added to the gateway unless GROQ_FREE_QUOTA_CONFIRMED=true.
The checked-in render.yaml keeps this flag false for new deployments; the live
service value is an operator-managed setting. This flag is confirmation of the
operator's quota choice, not a technical guarantee from Groq. If a configured
route is billed by its upstream provider, it must not be enabled under the free
profile. No model is silently substituted outside the explicit allowlist.

The FreeLLMAPI adapter records the model identifier returned in the API response
and rejects provider-reported identities outside the allowed set. If FreeLLMAPI
does not report its actual upstream model, the runtime keeps the distinction
between returned identity and configured alias; it must not pretend the alias
proves which upstream model ran.

## Free Render limitations

The current Omnitrix Render web service is on the free plan and has no persistent
disk. The FreeLLMAPI SQLite database therefore may reset when the instance is
replaced. The supervisor reseeds configured keys, the unified key, model
eligibility, and the free-route allowlist on each startup. Usage counters,
learned routing scores, and gateway operational state are not durable across a
fresh instance. The upstream provider still enforces its own limits, but the
gateway's local quota history must not be described as durable or authoritative.
If stable quota history becomes important, use a private service with persistent
storage and a reviewed backup/restore procedure; do not open FreeLLMAPI publicly.

A failed gateway build, unhealthy sidecar, missing secret, or empty eligible model
set disables the optional gateway and starts Omnitrix with its direct provider
profile when possible. This preserves the existing service, but it also means
FreeLLMAPI is unavailable until its startup failure is corrected.

## Verification checklist

Automated CI checks cover Python compilation, configuration JSON validation,
provider adapter behavior, model identity allowlisting, gateway fail-closed SQL
policy, ECC reference selection, and the existing Omnitrix regression suite.

Deployment acceptance is separate and must be based on real evidence:
- successful Render build and healthy Omnitrix service;
- internal FreeLLMAPI /api/ping success (observed by the supervisor);
- a live chat through freellmapi-auto-balanced returning a non-empty answer;
- returned model/provider identity captured truthfully;
- direct-route six-model smoke test with no paid fallback; and
- a successful Cline implementation attempt with changed-file/test evidence.

Passing unit tests alone is not evidence that upstream API keys are valid or that
all six models can currently return a live response.
