# Omnitrix rich-response formatting

**Status:** Implemented on branch `fix/universal-rich-formatting-2026-10-18`; validation runs through the repository CI workflows.

Omnitrix has two output surfaces with separate renderers: the browser-based Studio and the native Android application. Formatting is renderer behavior, not a prompt-only instruction and not a collection of character substitutions.

## Browser Studio

The browser chat turns assistant and user messages into sanitized GitHub-Flavored Markdown before inserting them into the page.

- **Structure:** headings, paragraphs, line breaks, unordered and ordered lists, task-style text, block quotes, horizontal rules, links, and GitHub-flavored tables.
- **Inline formatting:** emphasis, bold, strike-through, inline code, superscript/subscript HTML where safely admitted by the sanitizer, and images.
- **Equations:** inline `\\(...\\)` / `$...$` and display `\\[...\\]` / `$$...$$`, including fractions, roots, matrices, sums, products, integrals, limits, Greek characters, vectors, derivatives, and standard LaTeX constructs supported by KaTeX.
- **Code:** fenced and inline code, language highlighting, and a copy action.
- **Diagrams:** Mermaid fenced blocks (for example ```mermaid) render as SVG with Mermaid's strict security mode; malformed diagrams remain visible as code.
- **Security:** Marked's generated HTML is sanitized by DOMPurify before it is inserted. KaTeX is configured with trust disabled. External links open in a separate tab with `noopener noreferrer`. Mermaid output is sanitized again. If a library is not available, the renderer falls back to the original text rather than dropping the answer.

The renderer libraries are version-pinned CDN dependencies. When the device is offline or a CDN is blocked, rendering enhancements may be unavailable; the original answer remains readable as text. Mermaid is loaded only when a message contains a Mermaid block.

## Native Android

The old custom parser is replaced by the maintained Markwon renderer. It enables Markdown structure and inline formatting, tables, strike-through, task lists, safe HTML formatting, and LaTeX math using the JLatexMath extension. Links use the Android link movement method. Code remains readable with a monospace style provided by Markwon's renderer.

## Contract and known boundaries

No renderer can format every arbitrary dialect or every model-specific custom tag automatically. This implementation supports the common Markdown and LaTeX conventions explicitly listed above. Unsupported or malformed math/diagram syntax must remain visible or degrade gracefully, not silently fabricate a rendered result. The Python orchestrator/provider output contract is unchanged: renderers present returned content; they do not alter model reasoning or infer missing equations.

## Verification

The browser formatting test checks that the pinned dependencies, sanitize-before-insertion order, math rendering, code highlighting, Mermaid strict mode, fallback, and responsive styles remain wired together. Pull-request CI then runs the complete Python test suite and JavaScript syntax check; the Android workflow compiles and tests the Kotlin app and assembles an APK. Passing a static test is not a substitute for visually inspecting representative responses on device.
