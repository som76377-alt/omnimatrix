# Omnitrix Creative Studio — implementation and verification plan

## Checkpoint 2 — rigged 2D character engine

The local original-animation route uses a reusable deterministic vector character rig instead of the earlier hand-placed waving illustration. Named shoulder, elbow, wrist, hip, knee and ankle joints connect fixed-length limb segments. The renderer uses layered draw order, vector clothing, hair, face and hand shapes, and time-based poses for wave/greet, walk, run/jog, dance, jump/leap, nod and idle. It scales to selected output dimensions and feeds the existing WebM decode/motion QA.

This is a stylised 2D vector rig, not photorealistic footage or a full mesh-deformation/inverse-kinematics editor. It is a reusable foundation for custom character art, more motion clips and later rig editing.

The pose/kinematics core lives in `webapp/rigged-character.js`, separate from the Canvas renderer so the same action sampling can be tested without a browser. It resolves the brief to a named action, samples deterministic time-based channels, interpolates authored keyframes with smoothstep easing, and builds a parent-child skeleton with fixed segment lengths. The drawing layer consumes the sampled skeleton rather than maintaining a second copy of arm/leg pose math. Action regression tests exercise deterministic samples, actual joint displacement, jump motion, and segment lengths with Node's built-in test runner.

The rig remains stylised and intentionally local-first; it does not need model calls, generated images, external packages, or paid services. The browser recording/decoding/blank-frame checks remain the authority for whether an encoded clip is importable. The new kinematics tests do not replace an on-device visual review.


## Current milestone

This is the first creative-production milestone inside Omnitrix. The editor is a separate page at `webapp/creative-studio.html`, designed for phone-first use as well as desktop.

Integrated browser capabilities in this increment:
- Import multiple image and video files (up to 500 per selection), inspect metadata, generate small thumbnails, and keep original blobs in IndexedDB.
- Search the asset library by filename and retain local assets across reloads in the same browser profile, subject to browser quota and cleanup.
- Add source assets to a sequential edit timeline, reorder shots, change shot duration/source in-point, choose cover/contain framing, and apply simple pan/zoom presets.
- Add a title and subtitle to each shot with configurable position, colour, size and type style.
- Preview the edit on a canvas and export a local WebM draft, preferring broadly compatible VP8 WebM where the browser supports it.
- Capture canvas frames after painting when manual frame capture is available; otherwise use the timed captureStream fallback.
- Reopen and decode the original generated clip before importing it, sample encoded frames for blank output, and require measurable frame-to-frame motion for the original-animation route.
- Request a separate direct AI-generated MP4/WebM using the Gemini Interactions video model, with native audio/speech when supported. This requires explicit acknowledgement of paid usage (~US$0.10 per second at 720p; actual output can vary) and a separate click. It does not automatically fire when a chat prompt opens the Studio.
- Save the editable decision manifest as JSON.
- Search Wikimedia Commons using an authenticated asset-search route, display source/licence attribution, and import supported images/short clips from allowlisted HTTPS media hosts (24 MB per-file cap). Pexels is optional behind a server-side `PEXELS_API_KEY`; Pinterest is reference-search only and is not scraped or automatically downloaded.
- Build a zero-cost original vector/typography draft from a brief without an automatic web search. Online assets remain an explicit optional source mode. Metadata-based online selection is not visual proof; a prompt asking for a human/animal action or spoken dialogue is routed away from this fallback instead of being represented by a still image plus title cards.
- Let the schema-validated graphics engineer propose editable native text, rectangle, circle, line and arrow layers with bounded positions, size, opacity and restrained entry motion. A separate explicit auto-finish consent can apply validated supported edits to newly created shots and start a local WebM draft export.

This remains a first creative-production milestone, not a finished professional editor. The direct AI-video route is a real provider call, but its output is not an editable multitrack project, its quality is not guaranteed, and provider access/billing must be configured. Direct generation has bounded job limits, a 24 MB mobile transfer limit, and explicit paid-consent UI. The optional visual finish path can sample up to four midpoint frames from the local render and send them to the configured creative model under separate consent, apply supported changes and re-render once. This is not an independent critic and the corrected render is not reviewed by AI again. The export path now blocks output that cannot be decoded or whose majority of sampled frames are near-black/blank; the original-animation path additionally rejects clips where QA cannot detect frame-to-frame movement. A single isolated dark sample is a warning rather than an automatic rejection, to avoid misclassifying intentional dark shots.
The local editor still lacks true cross-dissolves, independent mixed audio tracks, masks, object removal, advanced colour grading and full 3D scene authoring.

## Direct AI video and audio generation

The current direct-generation model is `gemini-omni-1.1-flash` through the Gemini Interactions API. The provider can generate moving footage with audio from one prompt; it is deliberately distinct from the deterministic local Canvas/WebM graphics renderer.

The request requires a server-side `GEMINI_API_KEY` with paid video-model access and an owner-managed `OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA=true` environment flag (off by default). An owner must enable that flag after reviewing the cost. The interface requires the operator to check a separate cost-acknowledgement box and press **GENERATE REAL AI VIDEO + AUDIO**; a prompt arriving from Chat never silently authorizes a billable provider call. The estimate is about US$0.10 per generated second at 720p (approximately US$0.80 for an 8-second clip, but the final duration/provider accounting can vary). The public endpoint allows up to three requests per rolling day globally and two per source IP, plus two active server jobs. Mobile transfer is capped at 24 MB. A missing key, provider rejection, quota failure, missing output bytes, or oversized result must be surfaced as an error rather than converted into a fake success.

The image-generation endpoint was also updated to the current Gemini Interactions API and defaults to `gemini-nano-banana-2.1`. The previous `gemini-2.5-flash-image` default is migrated to the current model because that legacy model was shut down in October 2026. A 1K generated image is separately paid (roughly US$0.04 budget estimate); its own consent is not consent for video generation.

This is provider integration, not proof that the deployed key has paid access or that every output will be good. CI can test request assembly, validation and result parsing offline. Only a live provider invocation and inspection of the saved output on the target device verify the actual capability.

## Architecture decisions

1. **Phone-first browser shell.** Start with standard browser APIs and no heavy front-end package dependency. For canvas capture, use manual requestFrame capture when the browser exposes it and fall back to timed captureStream on browsers that do not. The user's Snapdragon 7 Gen 3 and 12 GB RAM are useful for thumbnailing and small local previews, but should not be treated as a guarantee that long 1080p/4K renders or generative model inference will fit within mobile thermal, memory and storage limits.
2. **Local-first media.** Originals stay in IndexedDB unless an explicit future feature asks to use a remote provider. The app must communicate browser storage use and never imply that IndexedDB is a permanent backup or available on another device.
3. **Structured, reversible edits.** The timeline stores source asset IDs and edit decisions separately from the original media. Editing does not mutate the input files.
4. **Deterministic tools before agent calls.** Media ingestion and supported timeline operations do not need a language model. This conserves model quotas and makes basic editing available even when every AI provider is offline.
5. **Honest agent status.** The media librarian and timeline executor are local deterministic functionality. Online discovery now has explicit provider scopes and licence metadata. The visual analyst/creative director/graphics engineer are opt-in through the authenticated Creative Studio API and require a configured provider plus per-run thumbnail consent. The finished-render visual critic is still not implemented. Never suggest that a model inspected search results, full videos or a final render unless that actually happened.
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
5. **General chat/tool bridge**: explicit video-creation prompts in the main web-chat UI now hand off to the dedicated Creative Studio route in the same tab and start the bounded draft workflow. This is an intent-guarded UI handoff rather than a reusable server-side orchestration tool, and it does not make arbitrary chat capable of calling the editor. Preserve explicit media-sharing consent and never expose arbitrary shell execution.
6. **Independent final QA**: the current optional path critiques up to four midpoint frames from the first rendered draft with the same model and permits one bounded correction/re-render; final output receives local decode and blank-frame checks. Still needed: an independent critic model, multiple/scene-change-aware frames throughout source clips, visual inspection of the corrected final output, and iterative render/inspect/correct loops with robust quality benchmarks.
7. **Remote render jobs**: add authenticated upload/download, a queue, background FFmpeg, per-job quotas and timeout/cancellation. Consider a separate hosted worker only when a real deployment is available and verified.

## Release gate for any AI visual claim

A feature may be labelled “AI visual analysis” only after a real configured model receives an asset or frame, returns an answer tied to stable asset IDs, and passes a test that detects incorrect or missing references. A feature may be labelled “AI quality review” only after the reviewer sees frames from the produced render—not just the source prompt—and identifies actionable defects. Offline tests prove code paths, not model quality or production availability.

## Sources checked
- FFmpeg.wasm official project and performance notes: <https://github.com/ffmpegwasm/ffmpeg.wasm> and <https://ffmpegwasm.netlify.app/docs/performance/>
- Video Ware source and license: <https://github.com/make-ware/video-ware>
- Hugging Face ZeroGPU quotas: <https://huggingface.co/docs/hub/main/en/spaces-zerogpu>
- Google Colab resource FAQ: <https://research.google.com/colaboratory/faq.html>
- GitHub Codespaces machine types: <https://docs.github.com/en/codespaces/customizing-your-codespace/changing-the-machine-type-for-your-codespace>
