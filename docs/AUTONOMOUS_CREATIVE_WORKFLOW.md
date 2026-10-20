# Omnitrix Creative Studio — prompt-to-video workflow

## What the feature provides

- Two distinct creation paths: (1) **Original motion-graphics draft**, which uses deterministic local Canvas scenes and renders WebM without searching or downloading online media, and (2) **Direct AI video**, which calls a dedicated video-generation model to create moving footage with native audio when supported. A human/animal action or spoken-dialogue prompt must not quietly degrade into a title-card slideshow.
- Wikimedia Commons search with attribution, source-page and licence metadata. Supported media downloads are allowlisted to official provider hosts and capped at 24 MB per imported file.
- Optional Pexels photo/video search when `PEXELS_API_KEY` is configured on the server. It is not required for the prompt-only workflow.
- Pinterest reference search links in the full web Studio. Pinterest Pins are **not** scraped or auto-imported; reuse media only through an authorised route with the necessary rights.
- The local **CREATE MOTION-GRAPHICS DRAFT** action starts with original graphics and is zero-provider-cost by default. It does not query Wikimedia, Google, Pinterest or any other media source unless a person explicitly changes the source mode. It makes a real local WebM from generated deterministic vector cards and supported motion presets; this is a lightweight draft, not a professional live-action scene.
- Image generation is a separate optional paid model request, currently configured for `gemini-nano-banana-2.1`, and is only invoked after the image/review consent is checked. The endpoint uses the current Gemini Interactions API, not the retired `gemini-2.5-flash-image` default. Failures must be visible and cannot be described as successful AI image output.
- **GENERATE REAL AI VIDEO + AUDIO** is a separate direct video-generation path using `gemini-omni-1.1-flash` through the Gemini Interactions API. It can return actual video with audio/speech instead of searching for existing footage or constructing a still-image slideshow. The UI requires a separate explicit paid cost acknowledgement and a separate button press; receiving a chat prompt never starts a paid video request automatically.
- The paid model is approximately US$0.10 per generated second at 720p (roughly US$0.80 for an 8-second clip, before possible duration/provider differences). There is no free-tier assumption. The server requires `GEMINI_API_KEY`, restricts active jobs, limits public submissions, and caps returned videos to 24 MB for mobile transfer. The provider may reject the request if the account/key does not have paid video access.
- AI-directed edits and post-render critique still use the separate consent-gated creative-director endpoint. A model/status label means a route is configured, not that it has successfully generated this file. Inspect the returned clip, motion continuity and audio before treating it as finished.
- Native editable text, rectangle, circle, line and arrow graphic layers, restrained motion presets and adjustable framing in the Studio.
- Local browser render and post-render technical QA: the output is reopened for decode metadata, duration, dimensions and sampled-frame checks. A consent-gated visual-director/post-render critic is available in the authenticated full web Studio when a supported model is configured.

## Android app integration

- The native app has a **Video** tab. An imperative request such as “Create a 12-second vertical science explainer video about an induction stove” sent from Chat switches to the Studio and begins the draft automatically. Regular questions and chat messages with attached chat files stay in chat.
- The Studio also opens directly from the Video tab, where the user can enter a brief manually. Image/video file picking is supported, but assets are optional because the automatic path searches Commons.
- On native Android, direct-generation requests go to bounded public API endpoints. The default graphics draft does not call the public asset search route. A direct AI video request uses a separately rate-limited job endpoint and requires an explicit paid consent action in the Studio.
- The native app saves local-rendered WebM and direct-generated MP4/WebM files to `Movies/Omnitrix` (on modern Android) and shows an **OPEN VIDEO** action. The native bridge accepts only MP4/WebM, with a 24 MB file limit.
- Prompts mentioning vertical/portrait, 9:16, Reels, TikTok or Shorts select 720×1280 output; square terms select 720×720; horizontal/landscape/16:9 selects 1280×720. Other prompts retain the current export setting.
- The native Studio can now query the server-side visual-model status and submit consented resized previews to the same structured director endpoint through a bounded mobile route. The mobile model endpoint is rate-limited per IP and globally; it still reports unavailable when no Gemini key is configured. Post-render critique only runs when consent is enabled and a model is configured.

## Quality and capability limits

Online results are optional and still ranked largely from searchable title/description/licence metadata; they are not proof that a result visually matches the request. Wikimedia Commons is an open-media archive, not a general search engine for every scene. Google Images and Pinterest remain reference paths unless a permitted source URL is explicitly imported. The local graphics mode is deterministic and intentionally not presented as full generative video. Direct AI video is a real provider generation request, but the provider output is not guaranteed to be good, to include dialogue correctly, or to satisfy every detail of a brief. It must be inspected before publishing. Preview critique sends only selected resized JPEG frames after separate consent; it does not inspect every frame, all source-clip motion, or audio.

The browser renderer uses Canvas + MediaRecorder and produces WebM. Native Android currently hands that renderer through a WebView. Actual playback/MediaRecorder behavior can vary by Android System WebView version, storage space and device; this code path must still be smoke-tested on the target phone after deployment. The app reports a save/render failure rather than claiming an export succeeded. Long or high-bitrate videos may exceed the mobile 24 MB limit; shorten the duration or choose a lower resolution if that happens.

The local Canvas editor still lacks true cross-dissolves, multitrack audio editing, advanced colour grading, masks/compositing, and a cloud post-processing/render queue. Those limitations do not stop the direct generation endpoint from returning a raw AI-generated video, but a generated video is not the same thing as a fully editable multitrack project. A configured route is not a live provider-health check, and neither model output nor anti-slop rules guarantee professional quality.

## How to use it

1. In Omnitrix on Android, send a creation prompt in Chat or open **Video**.
2. For an induction-stove diagram or typography-led explainer, use **CREATE MOTION-GRAPHICS DRAFT**. This follows the local zero-cost path and does not require stock footage.
3. For a scene requiring a person to move or speak (for example, “a man waves and says hi”), do not accept a still-card draft. Check **Approve one real AI-generated video**, review the estimate, then tap **GENERATE REAL AI VIDEO + AUDIO**. This is a paid API request and will not run before both actions.
4. Keep the Studio open while it polls the direct video job. The real returned video is saved as MP4/WebM to `Movies/Omnitrix` only after Android confirms the save.
5. Open the saved video and check movement, spoken audio, synchronization, and the actual model response. If the provider says paid access is missing or generation fails, the Studio must show that error rather than claiming a finished video.

## Security and licence boundaries

- Pinterest is reference-only until an authorised API/permission-based integration exists. The app does not bypass logins, rate limits or platform controls.
- The public native asset endpoints support Commons only, cap search results and apply per-client rate limiting; they are not a generic proxy or arbitrary URL fetcher.
- Original local media stays in the browser/WebView library. AI analysis sends resized previews and limited clip metadata only after consent; the native endpoint is bounded by per-IP and global rate limits. Full original media is not uploaded by this analysis path.
- Download URLs are provider-allowlisted, redirects are validated, MIME types are checked, and each imported asset is capped at 24 MB.
- The AI returns a structured proposal rather than executable code; client and server validators enforce operation allowlists and numeric bounds.
- Anti-slop guardrails reduce predictable layout and unsupported claims; they cannot guarantee visual quality. Inspect actual frames, timing, asset relevance, attribution and playback.

## Validation

CI covers Python backend/unit tests, browser JavaScript syntax and Android compilation/JVM tests. A green CI result does not replace a live run that searches a real provider, exports a WebM in Android System WebView, saves it to device storage and opens it in a player. That live target-phone check remains necessary after the changes are deployed.


## Google Images source integration (optional configuration)

Google's Custom Search JSON API is closed to new customers, so Google Images uses a manual reference fallback by default; a legacy API configuration is attempted only if already available. The Studio opens a query in Google Images, then users can paste a selected image's direct HTTPS image address into the URL importer. Search-result/page URLs are not direct image files. The importer rejects local/private-network targets, validates redirects, caps downloads at 24 MB, and accepts image files only. These user-selected images are marked rights-unverified; check the original source before sharing or publishing. The direct URL path also works with a chosen Pinterest-hosted image URL when it is publicly accessible.

Pinterest remains a user-directed reference search in this change. Automatic Pin scraping/download is not enabled. Users can save a chosen reference to Gallery and import it through the local multi-file picker, or paste a direct public image URL into the URL importer. A real Pinterest connection requires an approved official API/OAuth application and credentials; a reference link is not that integration.
