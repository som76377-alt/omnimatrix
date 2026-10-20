# Omnitrix Creative Studio — prompt-to-video workflow

## What the feature provides

- A prompt-driven workflow that searches the internet for licensed source media, creates a timeline draft, and renders a real WebM video locally in the browser/WebView. Manually adding images or video clips is optional.
- Wikimedia Commons search with attribution, source-page and licence metadata. Supported media downloads are allowlisted to official provider hosts and capped at 24 MB per imported file.
- Optional Pexels photo/video search when `PEXELS_API_KEY` is configured on the server. It is not required for the prompt-only workflow.
- Pinterest reference search links in the full web Studio. Pinterest Pins are **not** scraped or auto-imported; reuse media only through an authorised route with the necessary rights.
- A prompt-first **Create Video** action. It searches for source media, automatically broadens narrow Commons queries, ranks matches by title/description, imports up to four assets, arranges a short edit and starts a local WebM export. Manual asset picking is optional.
- If no supported source media can be imported, a local graphics fallback creates three original flat-vector scenes (title, process schematic and takeaway) and renders them as a basic motion-graphics explainer. This fallback is deterministic vector artwork, not photorealistic AI image generation.
- Native editable text, rectangle, circle, line and arrow graphic layers, restrained motion presets and adjustable framing in the Studio.
- Local browser render and post-render technical QA: the output is reopened for decode metadata, duration, dimensions and sampled-frame checks. A consent-gated visual-director/post-render critic is available in the authenticated full web Studio when a supported model is configured.

## Android app integration

- The native app has a **Video** tab. An imperative request such as “Create a 12-second vertical science explainer video about an induction stove” sent from Chat switches to the Studio and begins the draft automatically. Regular questions and chat messages with attached chat files stay in chat.
- The Studio also opens directly from the Video tab, where the user can enter a brief manually. Image/video file picking is supported, but assets are optional because the automatic path searches Commons.
- For the native app, the prompt-only path calls bounded, rate-limited public Commons endpoints. It does not require a Codespaces runtime token. This route is restricted to Commons rather than arbitrary download URLs, and it limits asset searches/imports.
- The native app saves a generated WebM to `Movies/Omnitrix` (on modern Android) and shows an **OPEN VIDEO** action. A bounded 24 MB video-file save limit is in place to avoid excessive memory use while passing WebM through the mobile bridge.
- Prompts mentioning vertical/portrait, 9:16, Reels, TikTok or Shorts select 720×1280 output; square terms select 720×720; horizontal/landscape/16:9 selects 1280×720. Other prompts retain the current export setting.
- The optional thumbnail-based AI director remains on the authenticated full web Studio path; native prompt-only generation does not claim an AI visual review. The native workflow still creates an actual local-rendered video even when no visual model is configured.

## Quality and capability limits

The initial automatic selection is based on searchable title and description metadata, not a model visually judging every search result. Commons files with incomplete licence metadata may be imported into a private draft, but this is not a claim that they are free to publish. Google Images is exposed as a reference link only; it is not scraped or auto-imported. When source search fails, the current fallback creates original vector graphics, not photorealistic AI images. The output remains a starter cut, not a finished professional documentary. Review it before publishing. The visual director on the full web Studio inspects resized thumbnails (one per source clip), not the full temporal content of the source clips.

The browser renderer uses Canvas + MediaRecorder and produces WebM. Native Android currently hands that renderer through a WebView. Actual playback/MediaRecorder behavior can vary by Android System WebView version, storage space and device; this code path must still be smoke-tested on the target phone after deployment. The app reports a save/render failure rather than claiming an export succeeded. Long or high-bitrate videos may exceed the mobile 24 MB limit; shorten the duration or choose a lower resolution if that happens.

True cross-dissolves, independently mixed music/narration tracks, advanced colour grading, masks/compositing, unrestricted internet crawling, provider-backed AI raster image generation, and a cloud render queue remain unsupported. These need separately configured providers or a real render worker; they must not be advertised as active. Pinterest is reference-only. A configured model status is not a live provider health check, and a model proposal is not a guarantee of artistic quality.

## How to use it

1. In Omnitrix on Android, send a direct creation prompt in Chat or tap **Video** to open the Studio manually.
2. Give one prompt including the subject, audience, duration, orientation and look. Example: “Create a 12-second vertical science explainer showing how an induction stove heats a pan; use purposeful labels and clean diagrams, no decorative particles or fake interfaces.”
3. Tap **CREATE VIDEO** or send the prompt from Chat. Omnitrix searches, assembles and attempts the export. Keep the Studio open. The WebM is saved to `Movies/Omnitrix` only when the bridge confirms the save.
4. Add local images or clips through the Studio’s file picker when you want to control the source media; this is optional.
5. Inspect the resulting video and confirm source/licence details before publishing. The native prompt-only mode is a starter edit, not a substitute for artistic review.

## Security and licence boundaries

- Pinterest is reference-only until an authorised API/permission-based integration exists. The app does not bypass logins, rate limits or platform controls.
- The public native asset endpoints support Commons only, cap search results and apply per-client rate limiting; they are not a generic proxy or arbitrary URL fetcher.
- Original local media stays in the browser/WebView library unless a user separately requests an AI visual-analysis operation in the authenticated web Studio. That opt-in sends resized previews rather than original media.
- Download URLs are provider-allowlisted, redirects are validated, MIME types are checked, and each imported asset is capped at 24 MB.
- The AI returns a structured proposal rather than executable code; client and server validators enforce operation allowlists and numeric bounds.
- Anti-slop guardrails reduce predictable layout and unsupported claims; they cannot guarantee visual quality. Inspect actual frames, timing, asset relevance, attribution and playback.

## Validation

CI covers Python backend/unit tests, browser JavaScript syntax and Android compilation/JVM tests. A green CI result does not replace a live run that searches a real provider, exports a WebM in Android System WebView, saves it to device storage and opens it in a player. That live target-phone check remains necessary after the changes are deployed.
