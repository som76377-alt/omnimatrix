# Omnitrix rich-response formatting

**Status:** Implementation is on `fix/universal-rich-formatting-2026-10-18`; it must pass CI and receive visual review before it is considered released.

Formatting belongs in the output renderers, not only in a prompt. Browser Studio and native Android use different rendering engines, so both need separate compatibility tests.

## Browser Studio

Assistant and user messages are parsed as GitHub-Flavored Markdown, sanitized, and then enhanced.

- **Document structure:** headings, paragraphs, line breaks, ordered and unordered lists, task-list text, block quotes, horizontal rules, links, images, and tables.
- **Inline text:** emphasis, bold, strike-through, inline code, and safely sanitized HTML formatting.
- **Mathematics:** inline and display TeX via `\\(...\\)`, `\\[...\\]`, `$...$`, and `$$...$$`; common equation environments; fractions, roots, matrices, sums, products, integrals, limits, Greek symbols, subscripts, superscripts, vectors, and derivatives within KaTeX's supported command set.
- **Physics notation:** common convenience macros `\\grad`, `\\curl`, `\\divergence`, `\\laplacian`, `\\vb`, `\\vu`, `\\dv`, and `\\pdv` are defined for common response conventions.
- **Chemistry:** KaTeX's `mhchem` extension enables `\\ce{...}` chemical equations/formula notation and `\\pu{...}` units syntax.
- **Code:** fenced and inline code, syntax highlighting, language labels, and a copy action.
- **Diagrams:** Mermaid fenced blocks render as SVG with strict security mode. Invalid diagrams remain as readable code.
- **Responsive layout:** math and tables are styled for message bubbles and narrow screens.

Markdown output is sanitized with DOMPurify before insertion. KaTeX runs with trust disabled; external links are opened with `noopener noreferrer`; Mermaid SVG is sanitized again. If a dependency fails to load, the original response remains readable as text/code instead of disappearing.

The pinned libraries are loaded from a CDN. Enhanced rendering therefore needs network access unless those assets are later vendored into the app. Version pins and Subresource Integrity hashes should be updated together.

## Native Android

The native renderer uses Markwon with tables, strikethrough, task lists, HTML formatting, and JLatexMath. Common model delimiters `\\(...\\)` and `\\[...\\]` are normalized into the dollar-delimited syntax supported by the installed Markwon LaTeX extension. Fenced code and inline code are protected from this normalization. Links use Android's link movement method.

The native renderer's TeX command coverage is narrower than browser KaTeX's; custom macros and specialized chemistry syntax that it does not support remain a known compatibility boundary. The browser's `mhchem` extension does not automatically apply to Android.

## Contract and boundaries

No finite renderer can format every arbitrary model-specific tag or every possible LaTeX package. This contract targets common Markdown, scientific notation and diagram formats. Unsupported or malformed syntax should stay visible or degrade gracefully, never be silently deleted or misrepresented. Rendering improves presentation; it does not improve the model's underlying reasoning or verify a scientific claim by itself.

## Verification

The browser regression test checks dependency pins and load order, sanitizer-before-insertion, math delimiter escaping, chemistry support, code highlighting, Mermaid strict mode and responsive styles. CI runs the full Python unit suite and JavaScript syntax checks; the Android workflow compiles/tests Kotlin and assembles an APK. Static tests are not a substitute for visual checks of representative equations, chemical reactions, tables, code and diagrams on both browser and Android.
