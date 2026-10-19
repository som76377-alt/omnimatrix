# Omnitrix Creative Studio — implementation and verification plan

## Current milestone

This is the first creative-production milestone inside Omnitrix. The editor is a separate page at `webapp/creative-studio.html`, designed for phone-first use as well as desktop.

Integrated browser capabilities in this increment:
- Import multiple image and video files (up to 500 per selection), inspect metadata, generate small thumbnails, and keep original blobs in IndexedDB.
- Search the asset library by filename and retain local assets across reloads in the same browser profile, subject to browser quota and cleanup.
- Add source assets to a sequential edit timeline, reorder shots, change shot duration/source in-point, choose cover/contain framing, and apply simple pan/zoom presets.
- Add a title and subtitle to each shot with configurable position, colour, size and type style.
- Preview the edit on a canvas and export a local WebM draft with source-video audio where the browser's MediaRecorder/Web Audio implementation supports it.
- Save the editable decision manifest as JSON.

This is a working editing foundation, not the finished elite editor. The current prototype does not yet offer independent music/narration tracks, true cross-dissolves, masks, object removal, advanced colour grading, 3D scene authoring, generative media transformations, or AI-driven visual analysis.

## Architecture decisions

1. **Phone-first browser shell.** Start with standard browser APIs and no heavy front-end package dependency. The user's Snapdragon 7 Gen 3 and 12 GB RAM are useful for thumbnailing and small local previews, but should not be treated as a guarantee that long 1080p/4K renders or generative model inference will fit within mobile thermal, memory and storage limits.
2. **Local-first media.** Originals stay in IndexedDB unless an explicit future feature asks to use a remote provider. The app must communicate browser storage use and never imply that IndexedDB is a permanent backup or available on another device.
3. **Structured, reversible edits.** The timeline stores source asset IDs and edit decisions separately from the original media. Editing does not mutate the input files.
4. **Deterministic tools before agent calls.** Media ingestion and supported timeline operations do not need a language model. This conserves model quotas and makes basic editing available even when every AI provider is offline.
5. **Honest agent status.** The media librarian and timeline executor are local deterministic functionality. The visual analyst, creative director and visual critic are configured as roles but are not live until a real provider adapter, consent path and verification tests are integrated. The user-visible UI must not suggest that an AI model has already analysed an image when no model call occurred.
6. **Separate render adapters.** Browser MediaRecorder is the first draft path. A native FFmpeg worker is the likely later production path for reliable codecs, separate audio tracks, transcoding and server-side renders. The worker must be authenticated, quota-aware and resumable.

## Tool/software review

### Integrated now
- Browser IndexedDB for local project/media persistence.
- Canvas 2D for compositing, title overlays, framing and motion presets.
- HTMLImageElement/HTMLVideoElement for browser-decoded preview sources.
- MediaRecorder + canvas.captureStream for local WebM draft rendering.
- Web Audio routing to capture audio embedded in source video clips when supported by the browser.

### Evaluated but not installed in this increment
- **FFmpeg.wasm** (<https://github.com/ffmpegwasm/ffmpeg.wasm>, MIT): useful for browser-side conversion and filters, but its maintainers report substantially slower transcoding than native FFmpeg; multithreaded execution uses more memory and CPU. Loading the full WASM engine by default would be a poor first choice for a phone-first page. Benchmark the actual formats and devices before installing it.
- **Video Ware** (<https://github.com/make-ware/video-ware>, AGPL-3.0-only): an interesting self-hosted, agent-editable multitrack editor with a CLI. Its documented development stack includes Node.js 22+, Yarn 4, FFmpeg, Redis and PocketBase. Optional semantic video analysis uses Google Cloud Video Intelligence. It is not a one-click free cloud dependency, and AGPL obligations need review before adopting or modifying it as a network service.
- **Blender** (<https://www.blender.org/>, GPL-3.0-or-later): the long-term specialist engine for 3D motion graphics, compositing and scientific animation. It is not claimed to be installed on this runtime yet.
- **Motion Canvas** (<https://motioncanvas.io/>, MIT): a later specialist for code-driven vector explainer animation and narration-synchronised graphics.
- **Hugging Face Spaces ZeroGPU** (<https://huggingface.co/docs/hub/main/en/spaces-zerogpu>): a useful way to test some GPU-backed demos, but the published free-account daily GPU quota is about five minutes and is intended for shared demos, not a guaranteed always-on render farm.
- **Google Colab** (<https://research.google.com/colaboratory/faq.html>): can provide occasional interactive experiments, but its free resource and GPU availability varies and is not guaranteed. It is not a dependable background worker for the production editor.
- **GitHub Actions / Codespaces**: useful for CI, builds and interactive development. Codespaces machine types vary by account and generally provide configurable CPU/RAM, not a guaranteed GPU render service. GitHub-hosted CI should not be presented as an unlimited media-processing backend.

## Free compute strategy

- Perform metadata extraction, thumbnailing, simple compositing, and draft rendering in the browser when possible.
- Never send all original references to an AI model in one prompt. Future indexing should create lightweight thumbnails/frame samples and retrieve only the assets relevant to the current task.
- Use remote model calls only for visual interpretation or creative decisions that actually require a model; require explicit consent before media leaves the browser.
- Later, offer a remote CPU FFmpeg job for heavier encoding, with queue state, size/duration caps, cleanup deadlines, cancellation, and resumable uploads. A remote GPU path is optional and must report its provider, quota, wait time, and limits honestly.
- Avoid making one free endpoint a hard dependency. When no model/worker quota is available, continue to allow local editing and explain which AI-only capabilities are unavailable.

## Next implementation phases

1. **Stabilise current editor**: UI and JS checks; test multiple-file imports, reload persistence, edit manifest, shot reordering, short WebM renders on Android Chrome and desktop Chrome.
2. **Project packaging**: media bundle export/import with checksums, browser quota warnings, undo/redo, stable asset identities, and autosave recovery.
3. **Multitrack editing**: independent music and narration tracks, waveform previews, volume automation, captions, trims, transitions and output presets.
4. **True graphic/motion workspace**: editable vector layers, shapes, typography and keyframes; then a Motion Canvas adapter for precise explainer graphics.
5. **Agent bridge**: wire the existing Omnitrix orchestrator through a new capability-limited creative API. Add explicit project permission to send selected images/frames; agents return schema-validated edit plans using real asset IDs. Never expose arbitrary shell execution.
6. **Visual critique loop**: sample the draft's actual rendered frames, compare with the brief and references, create actionable issue reports, and apply approved local changes.
7. **Remote render jobs**: add authenticated upload/download, a queue, background FFmpeg, per-job quotas and timeout/cancellation. Consider a separate hosted worker only when a real deployment is available and verified.

## Release gate for any AI visual claim

A feature may be labelled “AI visual analysis” only after a real configured model receives an asset or frame, returns an answer tied to stable asset IDs, and passes a test that detects incorrect or missing references. A feature may be labelled “AI quality review” only after the reviewer sees frames from the produced render—not just the source prompt—and identifies actionable defects. Offline tests prove code paths, not model quality or production availability.

## Sources checked
- FFmpeg.wasm official project and performance notes: <https://github.com/ffmpegwasm/ffmpeg.wasm> and <https://ffmpegwasm.netlify.app/docs/performance/>
- Video Ware source and license: <https://github.com/make-ware/video-ware>
- Hugging Face ZeroGPU quotas: <https://huggingface.co/docs/hub/main/en/spaces-zerogpu>
- Google Colab resource FAQ: <https://research.google.com/colaboratory/faq.html>
- GitHub Codespaces machine types: <https://docs.github.com/en/codespaces/customizing-your-codespace/changing-the-machine-type-for-your-codespace>
