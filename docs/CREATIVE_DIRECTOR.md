# Creative Studio AI direction

## Current workflow

1. Add image/video assets to the local Creative Studio library and add the shots you want to the timeline.
2. Open **Prepare AI Direction** and select up to six timeline shots. The panel lists the exact selected source names and the kind of preview being shared.
3. Review the displayed configured provider/model. Configuration status is not a live provider-health test.
4. Check the consent checkbox. The wording explicitly states that the call sends resized JPEG thumbnails and limited shot metadata to the configured provider and that provider quotas/charges may apply. Nothing is sent before the separate **Analyze selected previews** action.
5. The server checks consent, exact selected clip IDs, payload bounds, JPEG dimensions, and the provider route. It writes only those preview bytes to a temporary directory and passes those temporary JPEGs through the shared multimodal worker coordinator. No original source file, local project database, full asset library, or workspace path is sent.
6. The returned JSON is parsed and checked against the exact selected asset/clip ID pairs and a bounded operation allowlist. Unknown IDs, malformed JSON, unsupported operations, invalid styles, unsafe durations, and incomplete provider analysis fail closed.
7. The UI renders a readable summary, observations, worker/model identity, timing, and operation list. The plan does not modify the timeline until the user presses **Apply reviewed plan**. Application is validated again in the browser and aborted if the project timeline changed since the snapshot.
8. The accepted changes update local timeline state and use the project's existing local autosave/render flow.

## Supported proposals in this stage

- Per-shot duration (0.5–600 seconds).
- Existing framing fit (cover / contain).
- Existing motion presets (none, slow-zoom, zoom-out, pan-left, pan-right).
- Title, subtitle, title position/font/size/color.
- Whole-timeline order only when all current shots are explicitly selected and fit inside the six-shot batch.

## Not implemented by this stage

The lightweight director does not yet sample multiple frames throughout each original video, inspect or compare a final rendered video, or run an independent post-render visual critic. For videos it sees the browser-generated thumbnail, not the entire clip. It cannot add cross-dissolves or other between-shot transitions, soundtrack/music, narration, masks, generative object changes, or cloud rendering. These operations are explicitly listed as unsupported and rejected rather than approximated or silently ignored.

## Reliability and privacy boundaries

- The model proposes a plan; the deterministic validator decides whether that plan conforms to supported operations.
- File content and text visible inside images are untrusted data, never operational instructions.
- The backend does not execute model-generated code, shell commands, arbitrary HTML, SVG, or scripts.
- Analysis requests are token-authenticated, capped to six previews, bounded by compressed size and thumbnail dimensions, and serialized with a single-run lock.
- Provider timeout, missing keys, incomplete analysis, malformed JSON, invalid asset references, or unsupported operations return a failure rather than a success-shaped fake plan.
- Worker/model identity refers to the actual completed provider worker returned by the coordinator when available; status before a request shows configuration only, not a live health claim.
- The browser applies only the user's reviewed operations. That approval is not a claim that the edit is artistically perfect; inspect the rendered result before publishing.

## Path toward more autonomy without AI slop

The next meaningful layer should capture multiple evenly distributed and scene-change-aware frames from each source video, then render a low-resolution draft, sample the actual draft frames, and send those rendered frames to an independent critic. The critic should return only a structured defect list (e.g. title collision, blank frame, wrong order, unreadable text, bad crop, unexpected freeze), and a deterministic controller can patch supported edit parameters and re-render with a small retry budget. Quality gates should verify duration, black/blank frames, title safe areas, audio peaks/silence once audio is supported, and output decoding. Keep each iteration observable and reversible, then require final human approval. A model can still miss visual nuance; “no slop” is a target backed by tests and review, not a guarantee.
