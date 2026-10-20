# Shared Creative Production Coordination

## Decision

Omnitrix should coordinate a video through one production manifest and a dependency graph, not through several chat personas independently making assets. A background, diagram, arrow set, title system, or sound cue is created once, registered under a stable artifact ID, and then referenced by all downstream tasks. Specialists are responsible for different outputs, not duplicate versions of the same scene.

This document is the implementation contract. **It is not yet a claim that the runtime enforces the manifest.** The current Studio's graphics engineer and motion-designer labels still share one consent-gated creative-director model call; Manim, Motion Canvas and Blender are not yet integrated renderer adapters.

## Shared source of truth

Every video job must have a versioned manifest containing:

- **Brief and design system:** purpose, audience, style rules, aspect ratio, typography, colour, pacing and any prohibitions.
- **Scene plan:** stable scene IDs, purpose, duration, transitions, renderer assignment, camera/framing, audio cues, and dependency links.
- **Artifact registry:** stable IDs for each background, illustration, diagram, arrow group, label, texture, narration file and rendered scene. Each artifact has one owner, a producer task, a file/location reference, reuse policy, and verification state.
- **Task ledger:** task owner, scene IDs, the artifact IDs it may read/write, dependencies, status, manifest revision, and concrete output/evidence.
- **Render plan and QA:** exact renderer/codec settings, outputs, sampled frame/time checks, audio checks, defects, repair tasks, and final acceptance result.

Workers must read the same manifest revision before acting. They may only write outputs assigned to them. When one task changes an artifact, only its dependent tasks are invalidated. A task is not marked complete because a model says it is done; it must provide an artifact reference or a verifiable error.

## Division of work without duplication

1. **Director** owns the whole storyboard and shared design system. It divides a request into scenes and creates the dependency graph before any scene is built.
2. **Search planner / visual researcher** works per scene beat, not on the entire video prompt. It proposes multiple focused search phrases and source candidates with provenance. The visual critic or director determines whether the candidate actually fits.
3. **Asset builder** creates/imports a named artifact and registers it once. Later tasks use its ID rather than redrawing it.
4. **Renderer specialist** owns the scene's actual drawing and animation. If a Manim scene draws the background, axes, field lines and arrows, those belong to that scene artifact. Other workers can supply narration, camera timing, or text overlays as declared inputs, but must not recreate those elements.
5. **Coding agent** writes a bounded scene program against a tested adapter. It must use existing components/asset IDs first, run validation, and avoid rewriting unrelated scenes.
6. **Compositor** combines approved scene renders and audio. It does not create filler graphics when an upstream scene fails; failures remain visible in the job status.
7. **Critic** inspects actual exported frames and audio, reports defects tied to a scene/time/artifact ID, and creates narrowly scoped repair tasks. Final acceptance requires inspection of the corrected render.

## Renderer-routing policy

- **Motion Canvas:** the default candidate for editorial 2D motion design, typography, shape animation, transitions, and general-purpose explainers.
- **Manim Community:** use for mathematical and scientific visuals that benefit from exact coordinate systems, equations, vectors, graphs, and geometric constructions. It is not the default for every scene.
- **Blender:** use only for scenes needing 3D geometry, spatial camera movement, physical materials, or 3D compositing.
- **FFmpeg:** final assembly, audio mixing, transcoding, and technical media validation.

A scene may use a different renderer from its neighbour. The manifest determines the ownership boundary. Rendered scene clips are outputs that can be composed together; workers should not independently remake a background already contained in a registered scene.

## Search system policy

The video prompt is not itself an image-search query. Search must:
1. derive scene-level subjects/actions/objects;
2. create several concise query variants rather than only a literal whole-prompt query;
3. search multiple variants in priority order, deduplicate results, and retain which queries were attempted;
4. show provenance and licensing state with candidates;
5. use visual inspection before claiming a candidate matches the requested action;
6. distinguish a reference that is merely viewable from an asset that can be lawfully imported/reused.

Search-provider failures must not silently become success or a generic three-card video.

## Google Images and Pinterest

Google Images can be opened as real result pages for focused queries. Programmatic access is more constrained: Google's Custom Search JSON API is closed to new customers, so the Studio must not pretend it has a free official API for newly created projects. Current UX can provide multiple reference searches; a future browser-assisted picker must be tested for reliability and platform compliance before it is used to fetch/inspect image assets automatically.

Pinterest is currently reference-link only. An account-connected integration needs a real Pinterest developer app, approved API access, OAuth authorization, the necessary scopes, and compliant handling of user data. Do not ask for or store a Pinterest password or session cookie, and do not scrape Pins. API Trial access permits some read operations, but it has lower rate limits; Standard access has higher limits and requires an upgrade review. Account-connected boards/Pins are not the same thing as unrestricted global Pinterest image search.

## Current implementation status

- **Implemented in this change:** deterministic multi-query phrase planning for visual search; query variants are used across Commons and configured providers; Google/Pinterest reference results offer focused query links; the attempted queries are reported for traceability.
- **Still not implemented:** a manifest generated for each production job, manifest/task runtime validation, dependency-aware task execution, actual Manim/Motion Canvas/Blender adapters, one-time artifact reuse across renderers, and an independent critic that reviews the corrected final export.
- **Release rule:** never label a specialist as an independently working agent unless it has a real execution path and its output is recorded in the task ledger.
