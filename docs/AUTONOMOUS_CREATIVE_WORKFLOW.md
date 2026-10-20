# Omnitrix Creative Studio — online asset-to-draft workflow

## What the current feature branch adds

- A dedicated online-asset API in `core/creative_assets.py`, consumed by Creative Studio through authenticated server routes.
- Wikimedia Commons file search with attribution, source-page and licence metadata; supported media downloads are bounded to 24 MB and allowlisted official hosts.
- Optional Pexels photo/video search when `PEXELS_API_KEY` is configured on the server. Key availability and provider policy can change; it is not a required dependency.
- Pinterest search links for collecting references. Pinterest Pins are **not** scraped or downloaded by this app. A user must obtain permission and use an authorised route before reusing media.
- A one-action **Auto-assemble Draft** flow that searches up to 12 results, rejects unsupported formats or missing licence metadata, ranks by title/description matches, imports at most four selected assets, saves the source/rights metadata, and arranges a short sequential draft.
- An optional per-run consent checkbox that permits sending only the new draft shots' resized JPEG thumbnails to the configured visual model. If configured, the director can propose supported timing/framing/text/native graphic-layer changes; the client validates and applies that proposal to the newly created shots and starts browser WebM export.
- Native editable text, rectangle, circle, line and arrow graphic layers, with bounded opacity/size/position and restrained entry motion presets.

## What the workflow does not claim

Asset matching in Auto-assemble is currently based on searchable title, description and licence metadata. It does **not** visually inspect every internet result before it chooses the initial four. The opt-in multimodal director inspects those imported shots' resized thumbnails after the initial edit is made. Video analysis is one thumbnail per source clip, not full temporal understanding.

The visual director needs a working server-side `GEMINI_API_KEY` and configured model. A displayed configuration status is not a live health check. If the visual model is not configured or fails, the feature reports that and can still export the supported basic cut; it must not label that cut AI-reviewed.

The renderer remains browser-local Canvas + MediaRecorder WebM. The current build does not provide true cross-dissolves, independently mixed music/narration tracks, advanced colour grading, masks/compositing, generated raster imagery, a cloud render queue, a multi-frame final-render critic, or a bounded auto-correct/re-render loop. A successful browser download is not a substitute for opening and inspecting the exported file.

## Intended phone workflow

1. Open Creative Studio from the same core Studio tab in which the authenticated Python runtime is connected. Asset API routes require the runtime token.
2. Put the subject, audience, target duration, aspect ratio and style constraints in **Director's Brief**. For example: “Create a 12-second vertical science explainer showing how an induction stove heats a pan; documentary realism; two or three purposeful explanatory labels; no decorative particles or fake interfaces.”
3. Keep **Wikimedia Commons** selected for a no-key source, then press **Auto-assemble Draft**. The app only auto-imports supported formats whose search metadata exposes a licence name and licence URL.
4. Tick **Optional: let the Director + graphics engineer finish this draft** before starting the flow to grant one-run thumbnail sharing, automatic local application of validated supported edits, and automatic WebM export. This can incur upstream quota/charges, depending on provider. If unchecked, the app makes a basic timeline and leaves the model proposal step manual.
5. Review the local preview and exported WebM. Check the source and licence details for every asset before publication.

## Security and licence boundaries

- Pinterest is reference-only until an authorised API/permission-based integration is established. The feature does not bypass logins, rate limits, or platform controls.
- Only the bounded asset providers are supported by this endpoint; it is not an unrestricted general-purpose web crawler.
- Original local media is not uploaded for the director call. Only resized JPEG thumbnails and limited metadata for the consented new shots are sent. The source originals remain in browser IndexedDB, which is device-local and can be cleared by the browser.
- Remote images/video are downloaded only from provider allowlisted HTTPS hosts, with redirect validation, supported MIME checks, and a 24 MB maximum per file.
- The AI returns a structured proposal, not executable code. The browser has a second validator for operation type, asset/clip identity and numeric bounds.
- “Strict anti-slop” is a set of hard prompt rules plus bounded native operations, not a guarantee of artistic quality. Inspect every render; the current branch does not automatically critic the finished video.

## Validation target

Offline regression tests cover Commons metadata mapping, Pinterest reference-only behavior, missing Pexels key, unsafe download hosts, authenticated API access, graphics layer bounds, and allowed native arrow/line layer types. Provider search availability, model health, artistic relevance and browser MediaRecorder compatibility require a live smoke test with a configured runtime and a real phone/browser.
