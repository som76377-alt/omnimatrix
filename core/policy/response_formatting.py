"""Versioned output-format guidance for the Omnitrix chat renderer.

This nudges the model toward formats the clients actually support. It is a prompt
contract, not a guarantee; rendering is also covered by UI tests.
"""

from __future__ import annotations

RESPONSE_FORMATTING_POLICY_VERSION = "OMNI-RENDER-1.1"
RESPONSE_FORMATTING_POLICY_MARKER = (
    "[OMNITRIX RESPONSE FORMATTING CONTRACT: OMNI-RENDER-1.1]"
)

RESPONSE_FORMATTING_CONTRACT = r"""[OMNITRIX RESPONSE FORMATTING CONTRACT: OMNI-RENDER-1.1]
Use readable, semantically structured output that the actual Omnitrix chat renderer supports. Do not force special rendering into every answer; choose it when it makes the answer clearer.

1. GENERAL STRUCTURE
- Use standard Markdown headings, paragraphs, nested lists, links, and tables where a table genuinely improves comparison. Keep tables small enough to read on a phone.
- Use fenced code blocks with a language label for code. Keep code, JSON, terminal output, and literal syntax inside code fences so it is not mistaken for formatting.
- Do not emit arbitrary HTML, inline CSS, JavaScript, custom React tags, or raw SVG as a shortcut. Prefer the supported Markdown, math, Mermaid, and chart formats below.
- Cite relevant sources with real Markdown links when sources were actually consulted. Never invent citations or links.

2. MATHEMATICS AND SCIENTIFIC NOTATION
- Write inline TeX as \( ... \) or $ ... $, and display equations as \[ ... \] or $$ ... $$. Keep delimiters paired and put display equations on separate lines.
- Use supported KaTeX equation environments such as \begin{equation}...\end{equation}, \begin{align}...\end{align}, and \begin{gather}...\end{gather} as whole environments. Do not strip away the begin/end wrapper or wrap the environment in custom text.
- Use standard TeX for fractions, radicals, matrices, cases, sums, products, integrals, limits, Greek letters, subscripts/superscripts, vectors, and derivatives.
- Available convenience macros include \grad, \curl, \divergence, \laplacian, \vb{...}, \vu{...}, \dv{...}{...}, \pdv{...}{...}, \ket{...}, \bra{...}, \braket{...}{...}, \expect{...}, \abs{...}, \norm{...}, \evalat{...}{...}, and \dd.
- Put chemical formulas and reactions inside math delimiters using \ce{...}; for units use \pu{...}, for example \( \ce{2H2 + O2 -> 2H2O} \). Do not assume every LaTeX package is supported.

3. DIAGRAMS
- Use a fenced Mermaid block when a flow, dependency graph, sequence, state transition, data relationship, timeline, or other supported diagram is more informative than prose.
- Fenced math, latex, tex, katex, or equation blocks contain the equation itself and are rendered in display mode; do not wrap the contents in a second delimiter pair.
- For a direct browser-compatible media file only, use a fenced audio, video, or media JSON block with an HTTPS src. Playback is user-controlled; never autoplay. Do not invent media URLs or use iframe/platform watch-page embeds.
- Keep Mermaid syntax valid and minimal. Prefer flowchart, sequenceDiagram, classDiagram, stateDiagram-v2, erDiagram, gantt, mindmap, or timeline forms when they fit the task.
- Do not claim a diagram rendered successfully unless the renderer/preview was actually checked. If uncertain about Mermaid syntax, provide a simple valid diagram or describe the limitation.

4. DATA CHARTS
- Use a fenced `chart` block containing valid JSON for a simple native SVG chart when a chart genuinely helps.
- Supported chart types are `bar`, `line`, `scatter`, and `pie`. Bar/line/scatter use `{"type":"line","title":"Example","xLabel":"x","yLabel":"y","data":[{"x":0,"y":1},{"x":1,"y":3}]}`. Pie uses `{"type":"pie","data":[{"label":"A","value":3},{"label":"B","value":2}]}`. Multiple line/bar series use a `series` array with `name` and `data`.
- Chart data must be explicit inline values. Do not reference external URLs, scripts, expressions, or HTML in chart JSON. Use charts only when data is present or can be derived reliably; never invent points to make a chart look complete.
- Browser Studio renders chart blocks. Native Android currently preserves chart source as readable text instead of rendering a chart.

5. CALLOUTS AND FALLBACKS
- Use a GitHub-style blockquote callout only when a genuinely useful note/warning/tip needs emphasis:
  > [!NOTE]
  > Text of the note.
  Supported labels are `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, and `[!CAUTION]`.
- Keep formatting proportional to the task. A short direct answer should remain short; a complex tutorial can use deeper structure and the most helpful visual formats.
- Unsupported TeX packages such as TikZ/PGF/Pgfplots, custom interactive widgets, and arbitrary embedded media are not supported by the chat renderer. In those cases, use a supported artifact or explain the limitation instead of fabricating a visual.
"""

def with_response_formatting_contract(base_instructions: str) -> str:
    """Attach the versioned rich-rendering guidance exactly once."""
    if not isinstance(base_instructions, str) or not base_instructions.strip():
        raise ValueError("Base model instructions must be a non-empty string.")
    if RESPONSE_FORMATTING_POLICY_MARKER in base_instructions:
        return base_instructions
    return f"{base_instructions.rstrip()}\n\n{RESPONSE_FORMATTING_CONTRACT.strip()}"


def has_response_formatting_contract(instructions: str | None) -> bool:
    """Return whether renderer guidance is present in a model request."""
    return (
        isinstance(instructions, str)
        and RESPONSE_FORMATTING_POLICY_MARKER in instructions
        and RESPONSE_FORMATTING_POLICY_VERSION in instructions
    )
