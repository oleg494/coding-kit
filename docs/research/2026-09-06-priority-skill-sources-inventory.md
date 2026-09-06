# Priority skill sources — 50-row disposition inventory (2026-09-06)

Companion to `2026-09-06-priority-skill-sources.md` (split: main document hit
the 300-line limit). Method and source access log: main doc §1-§2. Owner:
fast-startup-check worker; read-only inventory, nothing installed or committed.

License column is **per-row status**, not a blanket claim: `fetched` = that
repo/skill's LICENSE or LICENSE.txt was retrieved raw on 2026-09-06; `not
fetched` = disposition does not depend on it; `unresolved` = fetch attempted,
404.

Disposition vocabulary:

- **adopted** — kit skill carries actual imported provenance (`> Source: …` footer or LICENSE attribution); no action.
- **overlap** — a kit skill functionally covers the ground; no import provenance claimed; no action.
- **adapt (hypothesis)** — candidate worth evaluating; NOT an approved new skill and NOT automatic. Any adoption needs a director decision plus the trigger test and evidence the kit's skill-authoring rules require.
- **reject — license** — upstream license forbids derivatives/distribution.
- **reject — kit constitution** — violates CONTRIBUTING rule 4 (no new runtime/MCP/daemons) as written.
- **defer** — no present measured need. This is NOT a claim that the domain is outside the kit's possible scope (the kit already ships design-system and dashboard-design, so UI/design work is in scope); it is a claim that no measured kit problem justifies the work now. Revisit if evidence appears.

Workbook popularity numbers are unverified marketing and were not used in any
disposition. No row recommends the workbook's `npx skills add` installer
(assignment: no installs).

| # | Skill / repo | License status | Kit relation | Disposition |
|---|---|---|---|---|
| 1 | find-skills / vercel-labs/skills | MIT (fetched) | skill-authoring (partial) | reject — constitution: discovery CLI adds an installer/ecosystem dependency the kit does not carry |
| 2 | grill-me / mattpocock/skills | MIT (fetched) | brainstorming | overlap |
| 3 | grill-with-docs / mattpocock/skills | MIT (fetched) | brainstorming, dev-wiki | adapt-idea only — its CONTEXT.md/ADR payload is row 14; grilling itself overlaps |
| 4 | improve-codebase-architecture / mattpocock/skills | MIT (fetched) | architecture-simplicity, code-graph-review | overlap |
| 5 | frontend-design / anthropics/skills | not fetched | design-system, dashboard-design | defer — no measured need; design is in kit scope, this is a page-generation procedure |
| 6 | tdd / mattpocock/skills | MIT (fetched) | test-driven-development | overlap |
| 7 | agent-browser / vercel-labs/agent-browser | Apache-2.0 (fetched) | harness browser tooling exists | defer — tool existence does not establish that a procedural browser skill is redundant; equivalence untested |
| 8 | handoff / mattpocock/skills | MIT (fetched) | none (dev-wiki is long-term memory, not session handoff) | **adapt (hypothesis)** — main doc §4.1 |
| 9 | triage / mattpocock/skills | MIT (fetched) | none | defer — depends on tracker setup + labels; kit is tracker-agnostic; no measured need |
| 10 | prototype / mattpocock/skills | MIT (fetched) | brainstorming Spike path | overlap |
| 11 | vercel-react-best-practices / vercel-labs/agent-skills | unresolved (root LICENSE 404) | none | defer — license blocker plus framework-specific; cannot reuse text while unresolved |
| 12 | web-design-guidelines / vercel-labs/agent-skills | unresolved (root LICENSE 404) | design-system | defer — same |
| 13 | teach / mattpocock/skills | MIT (fetched) | none | defer — no measured need |
| 14 | domain-modeling / mattpocock/skills | MIT (fetched) | none (dev-wiki is personal memory; CONTRIBUTING rule 6 keeps memory personal) | **adapt (hypothesis)** — main doc §4.2 |
| 15 | codebase-design / mattpocock/skills | MIT (fetched) | architecture-simplicity, spec-driven-development | overlap |
| 16 | diagnosing-bugs / mattpocock/skills | MIT (fetched) | systematic-debugging, debug-incident-protocol | overlap |
| 17 | implement / mattpocock/skills | MIT (fetched) | superpowers, incremental-implementation | overlap |
| 18 | code-review / mattpocock/skills | MIT (fetched) | code-review-and-quality, requesting/receiving-code-review | overlap |
| 19 | wayfinder / mattpocock/skills | MIT (fetched) | writing-plans (single-session), dispatching-parallel-agents | **adapt (hypothesis)** — main doc §4.4; heaviest (tracker dependency, body length) |
| 20 | design-taste-frontend / leonxlnx/taste-skill | MIT (fetched) | design-system | defer — no measured need |
| 21 | research / mattpocock/skills | MIT (fetched) | web-research | **adapt (hypothesis, merge not new skill)** — main doc §4.3 |
| 22 | to-spec / mattpocock/skills | MIT (fetched) | spec-driven-development | overlap |
| 23 | to-tickets / mattpocock/skills | MIT (fetched) | writing-plans, dispatching-parallel-agents | overlap (partial — ticket granularity appears in the wayfinder hypothesis) |
| 24 | resolving-merge-conflicts / mattpocock/skills | MIT (fetched) | git-workflow-and-versioning | overlap |
| 25 | supabase-postgres-best-practices / supabase/agent-skills | MIT (fetched) | none | defer — vendor-specific; no measured need |
| 26 | skill-creator / anthropics/skills | Apache-2.0 (LICENSE.txt fetched) | skill-authoring | overlap + pattern-mine only — eval/baseline/benchmark loop (main doc §4.5); no import of its viewer/scripts |
| 27 | brainstorming / obra/superpowers | MIT (fetched) | kit `brainstorming` footer: "Source: obra/superpowers (MIT)" | **adopted** |
| 28 | ui-ux-pro-max / nextlevelbuilder/ui-ux-pro-max-skill | MIT (fetched) | design-system | defer — no measured need; its long "pick me" description is the pattern main doc §3.3 warns against |
| 29 | brandkit / leonxlnx/taste-skill | MIT (fetched) | none | defer — no measured need |
| 30 | impeccable / pbakaus/impeccable | Apache-2.0 (fetched) | design-system | defer — no measured need |
| 31 | image-to-code / leonxlnx/taste-skill | MIT (fetched) | none | defer — harness vision tooling is not established as interchangeable with a procedural skill |
| 32 | systematic-debugging / obra/superpowers | MIT (fetched) | kit `systematic-debugging` footer | **adopted** |
| 33 | writing-plans / obra/superpowers | MIT (fetched) | kit `writing-plans` footer | **adopted** |
| 34 | pptx / anthropics/skills | **proprietary (LICENSE.txt fetched)** | none | reject — license: derivatives, distribution, sublicense banned verbatim |
| 35 | executing-plans / obra/superpowers | MIT (fetched) | superpowers IMPLEMENT phase, incremental-implementation | overlap — no kit folder of this name; functional coverage only |
| 36 | seo-audit / coreyhaines31/marketingskills | MIT (fetched) | none | defer — no measured need |
| 37 | verification-before-completion / obra/superpowers | MIT (fetched) | kit `verification-before-completion` footer | **adopted** |
| 38 | subagent-driven-development / obra/superpowers | MIT (fetched) | dispatching-parallel-agents (kit footer cites obra/superpowers, not this skill) | overlap — no kit folder of this name; kit LICENSE names it among upstream-derived provenance, but exact adoption is not demonstrable, so not "already in kit" |
| 39 | copywriting / coreyhaines31/marketingskills | MIT (fetched) | none | defer — no measured need |
| 40 | pdf / anthropics/skills | **proprietary (LICENSE.txt fetched)** | none | reject — license (same text as row 34) |
| 41 | docx / anthropics/skills | **proprietary (LICENSE.txt fetched)** | none | reject — license (same text as row 34) |
| 42 | xlsx / anthropics/skills | **proprietary (LICENSE.txt fetched)** | none | reject — license (same text as row 34) |
| 43 | webapp-testing / anthropics/skills | not fetched | kit Verify rules require browser verification for web UI changes | overlap — partial, unverified: no side-by-side comparison of the upstream procedure was performed |
| 44 | mcp-builder / anthropics/skills | not fetched | none | reject — constitution: CONTRIBUTING rule 4 bars MCP servers |
| 45 | web-artifacts-builder / anthropics/skills | not fetched | none | defer — no measured need |
| 46 | browser-use / browser-use/browser-use | MIT (fetched) | harness browser tooling exists | reject — constitution: Python agent framework is a new runtime |
| 47 | theme-factory / anthropics/skills | not fetched | design-system (tokens) | defer — no measured need |
| 48 | doc-coauthoring / anthropics/skills | not fetched | writing-plans, spec-driven-development | defer — no measured need |
| 49 | ponytail / dietrichgebert/ponytail | MIT (fetched) | kit `ponytail` Credits section names upstream + MIT | **adopted** |
| 50 | shadcn / shadcn-ui/ui | not fetched | none | defer — component-library-specific; no measured need |

## Counts (sum = 50)

- **adopted: 5** — rows 27, 32, 33, 37 (obra/superpowers, footer-provenanced) + 49 (ponytail, Credits-provenanced).
- **overlap: 13** — rows 2, 4, 6, 10, 15, 16, 17, 18, 22, 23, 24, 35, 38. Row 38 moved here from "already in kit": functional overlap, no demonstrable 1:1 import.
- **overlap, partial and unverified: 1** — row 43.
- **adapt (hypothesis): 4** — rows 8 (handoff), 14 (domain-modeling), 19 (wayfinder), 21 (research, merge into web-research). None is an approved new skill.
- **overlap-side specials: 2** — row 3 (adapt-idea only), row 26 (pattern-mine only).
- **reject — license: 4** — rows 34, 40, 41, 42 (all four LICENSE.txt fetched; identical proprietary text).
- **reject — kit constitution: 3** — rows 1, 44, 46.
- **defer (no present measured need): 18** — rows 5, 7, 9, 11, 12, 13, 20, 25, 28, 29, 30, 31, 36, 39, 45, 47, 48, 50. Rows 11-12 additionally carry an unresolved-license blocker; rows 7, 31 note that harness tool existence does not prove skill redundancy.

Count check: 5 + 13 + 1 + 4 + 2 + 4 + 3 + 18 = 50.
