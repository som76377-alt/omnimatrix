# Omnitrix Creative Studio — code-first video production contract

## Mandatory default workflow

Every prompt-to-video request must use code to construct the scene, animate it over time, render the complete video file, reopen/decode the actual exported file, inspect sampled rendered frames, and correct defects before calling the result finished.

The default prompt-to-video path is code-only:
- Do not search the web, Pinterest, Wikimedia, Pexels, Google Images, or any other asset source.
- Do not generate still images as a shortcut, then present them as the requested animation.
- Do not silently switch to stock footage, title cards, a slideshow, or unrelated placeholder assets.
- Write procedural scene/rendering code appropriate to the brief; animate actual scene state frame by frame; render a real video file.
- Run technical checks on the encoded output: it must reopen, decode, have the requested duration/dimensions within supported bounds, contain nonblank frames, and show meaningful motion when motion was requested.
- Run visual critique on sampled frames when the user explicitly permits sending those frames to the configured vision model. If remote visual review is not permitted or unavailable, label the result as an unapproved technical draft. Do not claim artistic approval.
- When the critic finds a meaningful mismatch, make a bounded correction and render/check again. If it still fails, stop and explain the failure instead of polishing the status message.

## Human and animal quality gate

The current local Canvas renderer produces stylised procedural graphics; it is not a photorealistic or high-fidelity human/animal renderer. Therefore a request whose main subject is a person or animal must be blocked before rendering rather than represented by crude lines, circles, or a barely recognisable waving figure. Do not call that a completed result.

This gate is intentional: the code-based high-fidelity character/3D renderer must be implemented and visually verified before human/animal action requests are accepted by the default code-only route. Never bypass this gate by searching for an image, generating a still image, or quietly invoking a different paid provider.

## Truthful status and limitations

- “Rendered” means an actual encoded file was produced and reopened.
- “Technical QA passed” means file/decode/motion checks passed; it does not mean the video looks good.
- “Visually approved” requires an actual visual critique of rendered frames against the brief.
- A configured model/tool is not evidence it ran.
- No request may be labelled finished when the output has not been inspected, has failed a quality gate, or cannot be produced with the available renderer.
- The separate manual media library/search controls are not part of prompt-to-video and must never be invoked by the default creation path.
- Paid video/image generation is not a fallback for this code-first contract and must not be triggered automatically.

## Implementation status

The prompt-to-video action now always enters the original code-rendering path, ignores the asset-source selector, does not generate an optional reference image, and blocks human/animal briefs until a high-fidelity code renderer exists. Technical export QA is separate from artistic approval. On-device testing and a visual-quality benchmark are still required before claiming production-grade output.
