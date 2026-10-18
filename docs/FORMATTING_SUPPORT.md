# Omnitrix rich-response formatting

**Scope:** Browser Studio and native Android have separate renderers. Support is a renderer feature, not just a prompt instruction. This document records the formats that have been implemented and their known boundaries.

## Model output guidance

User-facing chat requests receive the versioned `OMNI-RENDER-1.1` formatting contract from `core/policy/response_formatting.py`. It tells the model when and how to use supported TeX, chemistry, Mermaid diagrams, the data-only `chart` block, and semantic callouts. It is a prompt contract, not a guarantee that a probabilistic model will obey every instruction.

The task planner's strict JSON-only prompt deliberately does **not** receive this user-facing formatting contract, so machine-readable plans are not contaminated with presentation instructions.
## Browser Studio

Assistant and user messages are parsed as GitHub-Flavored Markdown, sanitized, and then enhanced.

- **Document structure:** headings, paragraphs, line breaks, ordered/unordered and nested lists, task-list syntax, block quotes, horizontal rules, links, images, tables, and safe inline HTML supported by the sanitizer.
- **Semantic callouts:** GitHub-style blockquote alerts using `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, or `[!CAUTION]` are converted to color-coded, accessible callouts.
- **Inline text:** bold, italic, strike-through, inline code, superscript/subscript through supported markup, and readable fallbacks for unsupported HTML/tags.
- **Mathematics:** inline/display TeX using `\(...\)`, `\[...\]`, `$...$`, and `$$...$$`; KaTeX auto-render's native equation environments; fractions, roots, matrices, cases, aligned equations, sums, products, integrals, limits, Greek symbols, subscripts, superscripts, vectors, derivatives and common physics macros.
- **Physics/quantum notation:** built-in helpers include `\grad`, `\curl`, `\divergence`, `\laplacian`, `\vb`, `\vu`, `\dv`, `\pdv`, `\ket`, `\bra`, `\braket`, `\expect`, `\abs`, `\norm`, `\evalat`, and `\dd`.
- **Chemistry and quantities:** the pinned KaTeX `mhchem` extension enables `\ce{...}` chemical formulas/reactions and `\pu{...}` physical units notation.
- **Code:** fenced/inline code, syntax highlighting, language labels, and a copy action.
- **Diagrams:** Mermaid fenced blocks render as SVG using strict security mode. Mermaid's supported diagram grammars include flowcharts, sequence, class/state, entity-relationship, Gantt, mind maps, timelines and other version-supported diagram types. Invalid diagrams remain readable as code.
- **Charts:** fenced `chart` JSON renders local, data-only SVG bar, line, scatter, and pie charts with axes, legends, point tooltips, title/description, and responsive overflow. It accepts inline values only; external data URLs, executable expressions, and arbitrary HTML are not supported by this renderer.
- **Responsive behavior:** equations and tables scroll horizontally when needed; charts remain legible on narrow screens.

Safety behavior: Markdown is sanitized by DOMPurify before insertion; KaTeX trust is disabled; external links open with `noopener noreferrer`; Mermaid SVG is sanitized again; charts are constructed via SVG DOM APIs rather than injecting model-provided SVG/HTML. If a renderer or CDN dependency fails, the underlying source remains readable. Chart specifications are constrained and capped to limit resource use.


### Chart block example

A chart is opt-in and data-only: put JSON in a `chart` fenced block. It renders in browser Studio; on Android the same JSON remains readable source until a native chart renderer is implemented.

```chart
{
  "type": "line",
  "title": "Position over time",
  "xLabel": "Time (s)",
  "yLabel": "Position (m)",
  "data": [
    {"x": 0, "y": 0},
    {"x": 1, "y": 2},
    {"x": 2, "y": 8},
    {"x": 3, "y": 18}
  ]
}
```

Multiple line/bar series use `"series": [{"name":"A","data":[{"x":0,"y":1}]}, ...]`. Pie charts use `"data": [{"label":"A","value":3}, ...]`. The renderer accepts only explicit local data and known chart types.
### Display math blocks and media previews

Browser Studio recognizes fenced math, latex, tex, katex, and equation blocks as display math. It also attempts top-level KaTeX environments such as equation, align, gather, alignat, and CD when they occur in normal text. Unsupported or malformed input is preserved as source instead of breaking the rest of the message.

Direct media previews can use a fenced audio, video, or media JSON block. The audio and video fence names imply the type; a media fence requires a type field:

```media
{
  "type": "audio",
  "title": "Audio preview",
  "src": "https://example.org/audio.mp3"
}
```

Only direct HTTPS URLs without embedded credentials are accepted. Players have user-controlled playback, never autoplay, use preload=none, suppress referrer transmission, include a source link, and surface playback failures. URLs must point to direct browser-compatible media files; watch pages and iframe embeds are not supported. These blocks are currently browser-only; Android preserves the source text.
## Native Android

The native renderer uses Markwon with tables, strikethrough, task-list syntax, HTML formatting and JLatexMath. Standard `\(...\)` and `\[...\]` math delimiters are normalized into syntax supported by the installed LaTeX extension, while fenced/inline code is protected. Markdown links use Android's link movement method.

Android does not currently render Mermaid diagrams or the custom `chart` JSON blocks as native diagrams/charts; those remain readable source on that surface. Its TeX command coverage is narrower than browser KaTeX's, and KaTeX's `mhchem` extension is browser-only. Unsupported commands should remain visible/readable rather than be represented as a verified rendering.

## Important limits

No finite renderer supports every TeX package, arbitrary model-specific tag, or every custom media type. In particular, TikZ/PGF drawings, Pgfplots, arbitrary LaTeX packages, notebooks, custom React components, interactive 3D/WebGL, and model-generated executable HTML are not implicitly supported. Use explicit artifacts or purpose-built viewers for those cases instead of trying to execute untrusted markup inside chat.

Rendering changes presentation; it does not establish whether a scientific equation or claim is correct. Visual inspection on real browsers/devices is still required in addition to static tests.

## Verification

The browser regression test checks dependency pins/order, safe Markdown insertion, standard math delimiters, chemistry support, advanced macro coverage, alert conversion, chart type/point caps, DOM-based SVG construction, code highlighting, Mermaid strict mode and responsive styling. CI runs the unit tests and JavaScript syntax checks; the Android workflow compiles/tests Kotlin and assembles the APK. These checks do not replace an end-to-end visual check of real examples.
