# Coordinated Agent Workflows

**Status:** partial, honest implementation. Creative Studio now exposes a science-diagram workflow: it validates user-provided causal steps, attempts the authenticated bounded Manim render API, falls back to a deterministic browser Canvas/WebM renderer when Manim is unavailable, imports the generated clip into the local library and timeline, and checks actual video decoding/sampled frames before delivery. A standalone manifest tracks the server-side Manim render task. This is not yet a fully coordinated multi-agent production pipeline.  
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

Manim now has a registered, constrained tool that generates a fixed Python scene from validated labels/coordinates/arrow indices; it never accepts arbitrary model-written source. Inputs are validated before a job is created; renders have a 90-second timeout and 24 MB Studio artifact cap, and output is written under `OMNITRIX_ARTIFACT_DIR` (default `/tmp/omnitrix-artifacts`). This is not a full isolated container: the host still needs normal process/container resource limits. The UI has a browser-renderer fallback; Manim installation and a real Manim render on the deployed host remain unverified.

## Runtime implementation checklist

- [x] Validate the coordination JSON configuration during CI.
- [x] Add a standalone typed manifest module with task ownership, dependencies, artifact references, state transitions, fingerprinting and optional atomic JSON persistence (`core/creative_production.py`).
- [x] Connect the user-facing science-diagram action to the Manim render/status/artifact API when available, plus a deterministic browser-render fallback; import the resulting clip into the browser media library and timeline. The manifest still does not cover every agent role or the whole timeline/export.
- [ ] Add shared artifact storage/manifest with checksums and provenance.
- [x] Add a bounded template-based Manim tool to the default tool registry; it accepts structured nodes/arrows only and refuses to claim availability if the `manim` executable is missing.
- [ ] Install/probe Manim in the deployed worker and run a real hosted MP4 render; the UI imports the returned MP4 when the Manim route works.
- [ ] Add worker adapters for visual inspection and FFmpeg; probe capabilities before routing.
- [ ] Add query expansion, result deduplication, relevance ranking and visual verification to asset search.
- [ ] Add independent critic routing and final-export inspection.
- [ ] Add per-provider timeout, cancellation, bounded retry and cost controls.
- [ ] Add integration tests for parallel dependency execution, no duplicate ownership, failed worker handoff, cost-consent enforcement and final QA failure.
- [ ] Verify the target deployment and mobile app against a real test job.

This design is not complete until the runtime checklist is implemented and tests run. Do not describe this staged contract as an operational multi-agent system.


## Current honest status

The shared manifest module and Manim tool now have API/UI integration tests in CI, and the science diagram can be created locally without paid AI services. The server-side render queue remains in memory, so job records are lost on restart. The manifest is not yet the shared source of truth across researcher, graphics, Manim, editor and critic roles; no independently deployed full-video/audio critic or durable queue exists, and the deployed Render host's Manim executable/actual render remains unverified. Browser decode and sampled-frame checks are technical QA, not proof of scientific correctness or zero AI slop. Do not describe the remaining orchestration as complete.
