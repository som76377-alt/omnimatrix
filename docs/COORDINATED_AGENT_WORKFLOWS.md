# Coordinated Agent Workflows

**Status:** design contract staged on `feat/coordinated-agent-workflows`; this file is not yet connected to the runtime.  
**Purpose:** prevent role-labelled agents from duplicating work, losing context, inventing tool success, or producing an unchecked final artifact.

## Non-negotiable architecture

Omnitrix remains the single orchestrator. Specialist roles do not own separate objectives, permissions, budgets, or final decisions. The orchestrator creates one job brief and dependency graph, assigns bounded work packages, records artifact IDs and provenance, and evaluates acceptance criteria.

A role name is not proof of a separate model. A tool marked integrated is not proof that the remote credential, runtime, or deployment is healthy. Report configured, reachable, executed, and verified as four different states.

## Shared job contract

Every run should persist a versioned job brief containing:
- objective, deliverable, format, target platform, audience, constraints, assumptions and acceptance checks;
- budget and whether any paid/provider call is approved;
- a dependency graph with explicit task owner, input artifact IDs, output artifact IDs and status;
- a shared artifact manifest with checksum, source, license/attribution, dimensions/duration and validation status where relevant;
- model/tool identity, execution status, bounded retry count and safe failure reason;
- final QA findings and unresolved limitations.

A downstream role must consume upstream artifact IDs and results, not reconstruct the entire task from the original prompt. Treat all model-produced content and downloaded assets as untrusted until validated.

## Example: science explainer video

1. **Intent engineer** writes the brief and acceptance tests (subject accuracy, aspect ratio, duration, audience, target export).
2. **Researcher** verifies the scientific mechanism and records source-backed claims.
3. **Asset scout** runs several query variants and searches by object, mechanism, visual synonym and scene context. It scores candidates by relevance and rights metadata. A visual analyst verifies actual pixels before selection; titles and filenames alone are not enough.
4. **Work allocator** reserves task ownership. The graphics engineer owns original arrows, labels, schematics and explanatory motion; the Manim worker owns only assigned mathematical/scientific scenes; the media editor owns the timeline, shot order, transitions and final export. They share a scene/asset manifest so no two roles recreate the same item.
5. Independent tasks can run in parallel. A task with an unmet dependency waits rather than making up missing inputs.
6. **Media editor** assembles the approved artifacts and preserves expected audio. Heavy rendering is routed to a verified worker rather than assumed to run well on a phone.
7. **Visual analyst** inspects source assets and the rendered result, including scene changes and key frames. **Critic** receives the actual candidate export plus acceptance criteria, not just another agent's description.
8. A failed check creates a specific correction task owned by the responsible role. Re-render only affected work where dependencies allow, then re-inspect the corrected final export.
9. The orchestrator returns the deliverable, test/QA report, sources/licences, actual model/tool use, cost status and remaining limitations.

## Search policy

For each important visual concept, produce multiple narrow queries rather than one broad query. For example, split an induction stove into coil, alternating magnetic field, eddy currents, pan base, heat transfer, and final cooking scene. Use synonym expansion and object/action/context variants; deduplicate by source ID and perceptual similarity; rank by actual visual relevance, rights status, resolution and suitability for the target shot. Do not assume Pinterest or Google Images search results may be scraped or reused.

## Model and tool selection

Use Gemini image generation for consented raster generation/editing; use the configured Gemini video route only after separate cost consent; use OpenRouter/Nemotron for eligible text reasoning when the live route is healthy; use deterministic calculators and media probes for exact computation and technical checks. A model should not be used where a deterministic tool is more reliable.

Manim is a good candidate for reproducible mathematical and scientific animations, but it is **not yet runtime-integrated by this configuration**. Before enabling it, add a sandboxed worker, pin dependencies, probe the executable/version, set CPU/memory/time/output limits, validate generated files, and test one representative scene. Do not run model-generated Python with unrestricted host access.

## Runtime implementation checklist

- [ ] Load and schema-validate `config/coordinated-agent-workflows.json`.
- [ ] Add typed task ownership, dependencies, artifact references and state transitions to the runtime.
- [ ] Add shared artifact storage/manifest with checksums and provenance.
- [ ] Add worker adapters for asset search, visual inspection, Manim and FFmpeg; probe capabilities before routing.
- [ ] Add query expansion, result deduplication, relevance ranking and visual verification to asset search.
- [ ] Add independent critic routing and final-export inspection.
- [ ] Add per-provider timeout, cancellation, bounded retry and cost controls.
- [ ] Add integration tests for parallel dependency execution, no duplicate ownership, failed worker handoff, cost-consent enforcement and final QA failure.
- [ ] Verify the target deployment and mobile app against a real test job.

This design is not complete until the runtime checklist is implemented and tests run. Do not describe this staged contract as an operational multi-agent system.
