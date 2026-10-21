# Omnitrix agent operating contract and anti-slop gates

**Purpose:** make coordination, ownership, handoffs, and review explicit. This contract complements the runtime policies; it is not model training and cannot prevent a model from internally considering adjacent ideas. Runtime tool allowlists can enforce which registered tools a role may call. The role prompts and acceptance gates constrain the work product.

## 1. One coordinator, one source of truth

Omnitrix is the control plane. It owns the original user objective, intent brief, priorities, budget/permissions, run state, assignment map, dependency order, conflict resolution, integration, and final report. For complex work involving multiple roles, the orchestrator model stage selects an eligible model using its configured preference order and proposes a validated work-package plan; the primary lead model owns execution and final integration. Models are selected only from enabled, available, capability-compatible and budget-eligible candidates. Role preference and availability are routing evidence, not proof that the selected model is objectively the smartest. Do not announce a universally "most capable" model until a common benchmark supports that conclusion.

The lead model coordinates the assigned specialists, consumes their findings, resolves contradictions against the user's request and source evidence, and produces the integrated result. A supporting specialist must return only its bounded work product; it must not silently replace the lead or redo everyone else's task. Each handoff must include the objective slice, constraints, prior accepted artifacts/findings, expected output, dependencies, and measurable acceptance checks.

**Important reality check:** the core currently has eight configurable model-role policies: orchestrator, intent engineer, reasoning, coding, subject solver, research, computation, and critic. Those role names do not imply seven distinct underlying models. The main mobile model profile currently registers a Gemini route and an OpenRouter Nemotron route plus a fallback profile; provider keys alone do not register a model or implement an adapter. The current core research role does not have a native live web-search tool. Report configured, available, called, and verified as separate states.

## 2. Exclusive role ownership

| Role / worker | Owns | Must not do |
|---|---|---|
| Intent engineer | Distill intent, deliverable, constraints, assumptions, complexity, dependencies, acceptance checks into the required brief | Answer the user's substantive question, research, code, or use tools |
| Orchestrator model stage | On complex multi-role work, assign one bounded work package per active supporting role, specify dependencies/acceptance checks, set integration order and prepare a Cline handoff when appropriate | Solve the subject task itself, code, research, calculate, call tools, pretend unrun specialists are active, or change the user objective |
| Reasoning specialist | General logic, causal reasoning, options, trade-offs and decision support | Claim to have searched, coded, run exact computation, or performed artifact QA without evidence |
| Research specialist | Source retrieval and source/claim validation when actual retrieval tools and results exist | Invent citations/searches or present stale memory as live research; silently code or perform final critique |
| Subject solver | Domain-specific scientific, mathematical, engineering, humanities or other assigned subject model and interpretation | Take over code edits, unsupported live research, or final visual inspection; delegate exact calculations when a separate calculation job is assigned |
| Computation specialist | Exact numeric/arithmetic work, symbolic/numeric cross-checks that tools support, units and sanity checks | Replace the subject model, search for sources, edit code, or author the entire response |
| Coding specialist | Understand repository architecture, choose implementation approach, define testable requirements and review the patch/test evidence | Claim files changed or tests passed without evidence; do not impersonate the execution worker |
| **Cline implementation executor** | When invoked by the coding specialist, inspect the authorized workspace copy, implement the scoped patch, run relevant tests, report changed files and actual outcomes | Is not a separate registered LLM model in AgentRegistry; must not do general reasoning/research/design for the team, alter unrelated files, or claim success without command/output evidence |
| Critic | Adversarially review the integrated output against the brief and acceptance checks; return a concrete pass/revise result | Rebuild the whole deliverable, edit files, add unsupported claims, or pretend same-model review is independent |

These are explicit role/output boundaries, not a claim that each role has a unique model. The active configuration and run trace determine which model actually ran each stage.

## 3. Routing and tool boundaries

- The intent and critic stages are analysis-only, with no tools.
- Cline coding is available only to the coding role; workspace inspection is scoped to coding tasks.
- Calculator is scoped to computation and subject solver; the latter may use it only as a numerical aid to its assigned subject task.
- The Manim scientific diagram renderer is scoped to subject solver for scientifically grounded, structured diagrams. It is a constrained renderer, not a general code-execution facility.
- Reasoning and research receive no core tools by default. The current core registry has no live web-search tool, so research must state that limitation rather than inventing sources.
- Unknown role IDs receive no tools. Plan scopes, user permissions, budget checks, argument validation, and role allowlists are cumulative; passing one is not a substitute for the others.
- If the requested specialist or an appropriate tool is unavailable, the coordinator must mark the work blocked/unverified and either complete only the part it can honestly do or report the blocker. It must never silently route work to a different specialist and label it as the requested one.

Prompt boundaries help; code-level tool gating is authoritative for registered tool calls. They do not sandbox the model's hidden internal reasoning or replace operating-system isolation.

## 4. Required handoff record

For complex work, the coordinator's task brief must preserve:
1. User objective, deliverable, audience/platform, hard constraints, assumptions, budget/permission status and acceptance criteria.
2. A work map with one accountable owner per output, exact input artifacts/findings, dependencies, expected format, target files/scene/shot, and test/QA evidence.
3. Handoff packets with only relevant upstream findings; source URLs/licences or artifact IDs and checksums where applicable.
4. Integration decision: how each result maps into the final artifact, which conflicts were resolved and why, and which requirements remain unsatisfied.
5. A final evidence ledger distinguishing configured, available, executed, passed, failed, not run, and unverified.

A downstream agent consumes the previous accepted result; it must not re-plan from scratch unless an upstream result conflicts with the user brief or fails validation. On failure, reopen only the failed dependency/owned output where practical, then re-run dependent checks.

## 5. Strict design and creative anti-slop guardrails

Design quality is judged by the rendered result and how well it serves the task, not by elaborate descriptions or number of effects.

### Layout, interface and product design
- Establish one obvious hierarchy: a meaningful primary action, readable typography, intentional spacing, contrast, and a consistent grid. Mobile layouts must work at narrow viewport widths before desktop polish.
- Avoid generic AI-template aesthetics: purple/blue gradients by default, overused cards, pill buttons, random rings/circles, corner ornaments, floating particles, fake HUDs, glowing outlines, cursor trails, background noise, and decorative motion. Use them only if a documented purpose and user request justify them.
- No fabricated reviews, counts, counters, social proof, badges, ratings, feature claims, or "live" indicators, or placeholder content presented as real.
- Icons should be real, consistent and semantically useful; no emoji substitutes for production icons. Avoid unnecessary pills, panels, card grids, and repeated identical section templates.
- Interaction must have actual behavior, clear focus/keyboard states, accessible labels, touch-sized controls, responsive layout, error/empty/loading states and sensible reduced-motion behavior. A pretty static mock is not a functioning feature.
- Animation must explain state, hierarchy, cause/effect or navigation. Avoid scroll-jacking, long blocking transitions, animation loops without purpose, and effects that delay reaching content. Respect reduced motion.
- Do not invent a new visual system if a good existing design system or project component already exists. Reuse shared primitives and tokens before creating parallel ones.

### Science, motion graphics, 3D and video
- Correct causal order and spatial relationships outrank decoration. Use code-native diagrams, geometry, labels, arrows, timelines, 3D scenes or compositing when these are the requested deliverable and the renderer can produce them. Do not substitute a generated still, search thumbnail, stock image, or UI mock for an explicitly requested rendered animation/video.
- Every added arrow, label, overlay, shape or camera movement must explain the mechanism or direct attention. No random particles, decorative circles, filler labels, fake HUDs/metrics, gratuitous glow, arbitrary object slicing, or motion merely to look "AI-made".
- Preserve object continuity, scale, plausible materials, silhouette and causal geometry. No arbitrary pizza-slice/exploded-view breakup unless technically correct and explicitly wanted.
- Search, if available, uses multiple specific query variants for individual subjects, mechanisms and scene beats; deduplicate candidates and validate the actual image/video frames instead of trusting titles. Respect licence and source metadata. Never claim an asset is visually verified if only its title was inspected.
- A render's existence is only technical evidence. Validate duration, aspect ratio, decode/frame integrity, output dimensions and expected audio, then visually inspect representative frames (and audio when relevant). Critic must review the actual rendered artifact, not merely a description or prompt.
- If the required renderer/tool is not installed or cannot produce the requested output, say so and offer a truthful partial result; do not rename a still image or preview into a rendered video.

## 6. Code and artifact definition of done

A task is not complete because a prompt, checklist, design description, patch or render command exists. It is complete only against the declared acceptance checks.

- Inspect the existing implementation, user requirements and project design/architecture before changing it.
- Make the smallest coherent implementation; preserve useful work already completed by other roles.
- Run targeted unit/integration checks and the repository's relevant build/type checks. Inspect test output and fix regressions rather than weakening tests.
- For UI/video/design, inspect the actual rendered screen/export at real target dimensions. For code, read the final diff and changed-file list. For scientific content, verify the causal model and calculations independently where possible.
- Critic reports concrete evidence-based defects, not vague taste. The owner of a failed artifact receives a narrowly scoped correction request.
- Final reports say what changed, which actual models/tools ran, what tests/visual checks passed or failed, and what remains unverified. No "done" claim for work that has not been executed and checked.

## 7. Enforcement boundary

The repository can enforce role-based tool access, schemas, budgets, path allowlists, task state, and required policy presence. Prompts and JSON files cannot guarantee expert-level output or prevent internal cross-domain reasoning. Six provider secrets do not themselves create six AI workers, and Cline is an actual coding-agent CLI invoked as a tool/worker, not a separate registered base model. Live end-to-end coordination is only confirmed by a trace showing the participating model stages, actual Cline execution, accepted changes and tests.
