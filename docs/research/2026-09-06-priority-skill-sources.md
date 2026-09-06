# Priority skill sources — inventory and source verification (2026-09-06)

Status: research deliverable — inventory and source verification only. Owner:
fast-startup-check worker. No installs, no npx, no global changes, no commits;
no kit files edited. Core instruction edits are owned by the product-evidence
worker (hub-confirmed: no file overlap).

Inputs assigned: `top50skils.xlsx` (all 50 rows), X post
`pvncher/status/2095991462416490862`, `github.com/openai/skills`,
`developers.openai.com/api/docs/guides/latest-model`. Method per the kit
web-research skill: each fact cites its exact source, with primary vs mirror
labelled; unverified items are marked as unverified.

## 1. Source access log (what was reachable, how)

| Source | Access path | Result |
|---|---|---|
| top50skils.xlsx | `read` (converter) + stdlib `zipfile`/`xml.etree` re-parse of `xl/worksheets/sheet1.xml` + `xl/sharedStrings.xml` | All 50 rows extracted twice, consistent (155 sheet rows incl. header/promo; exactly 50 numbered rows) |
| x.com/pvncher/status/2095991462416490862 (primary target) | Direct x.com read blocked. **MIRROR, not primary**: `https://api.fxtwitter.com/pvncher/status/2095991462416490862` returned structured JSON of the X article body. Full fetched payload preserved this session at `artifact://135` | Content identified: X article "Rethinking skills and prompts for GPT-6 Astra", eric provencher (@pvncher, bio "Codex DX @Openai"), created 2026-09-04T21:44:40Z, article id 2095989703967125509. Every §3.3 claim traces to that mirror payload; none was read on x.com itself |
| same article, corroboration | web_search (per web-research skill: ≥2 sources) | **Secondary retellings only**, not primary: explainx.ai guide (2026-09-04), the-decoder.com, x.com/joedevon/status/2095996826596024745. They agree on author/date/title/substance; they do not substitute for x.com |
| github.com/openai/skills | GitHub-API-backed read | README carries official deprecation banner (verbatim in §3) |
| developers.openai.com/api/docs/guides/latest-model | direct read (`.md` suffix variant) | Full guide fetched incl. all prompt blocks |
| developers.openai.com/plugins/build/skills, /build/plugins | direct read (`.md` suffix) | Full current build guides fetched |
| github.com/openai/plugins | repo read + raw.githubusercontent LICENSE | Repo exists (5,410 stars); **no root LICENSE (raw 404)**; `plugin-creator` skill dir has no LICENSE.txt |
| api.github.com/repos/openai/plugins | direct | HTTP 403 (rate limit) — license metadata not confirmable via API; raw-404 stands as evidence |
| Upstream SKILL.md files (handoff, wayfinder, research, domain-modeling, both skill-creators, plugin-creator) | raw.githubusercontent.com | Fetched verbatim (quoted in §4) |
| Upstream LICENSE / LICENSE.txt files | raw.githubusercontent.com | **Per-item, not blanket.** 16 raw fetches succeeded; 2 attempted → 404 (`openai/plugins` root, `vercel-labs/agent-skills` root); 1 from repo metadata only (`vercel-labs/skills`); rest not fetched. §2 |

## 2. Workbook verdict and repo-level facts

The workbook is a Russian-language promo sheet for a Telegram channel
(t.me/inclient, "Бегин"); every row carries channel advertising cells and a
`npx skills add ...` quick-start. Its 📥 install counts come from skills.sh and
were **not independently verified**; its ⭐ counts are stale but same order of
magnitude as GitHub API values fetched today (mattpocock/skills: sheet 244.2k
vs actual 252,891; obra/superpowers: 280.5k vs 282,140). Per assignment,
popularity is treated as marketing, not quality; dispositions rest on kit
overlap, per-source license status, and kit constitution (CONTRIBUTING.md).

License status per source (2026-09-06). `fetched` = raw file retrieved and read; `metadata` = repo API/GitHub read only; `404` = fetch attempted, absent:

| Source | License status | Evidence |
|---|---|---|
| mattpocock/skills | MIT © 2026 Matt Pocock — fetched | raw LICENSE, full text |
| obra/superpowers | MIT © 2025 Jesse Vincent — fetched | raw LICENSE, full text |
| anthropics/skills `skill-creator` | Apache-2.0 © 2026 Anthropic PBC — fetched | raw `skills/skill-creator/LICENSE.txt` |
| anthropics/skills `docx`, `pdf`, `pptx`, `xlsx` | **proprietary source-available — each LICENSE.txt fetched individually** | All four raw files retrieved; identical text: "© 2025 Anthropic, PBC. All rights reserved." ADDITIONAL RESTRICTIONS bar extraction/retention outside the Services, reproduction, "Create derivative works based on these materials", "Distribute, sublicense, or transfer these materials to any third party", reverse engineering |
| openai/skills `.system/skill-creator` (deprecated repo) | Apache-2.0, boilerplate copyright field unfilled — fetched | raw LICENSE.txt |
| openai/plugins | **none found** (raw root LICENSE 404; no License line in repo metadata; API 403) | §1 access log |
| vercel-labs/skills (npx CLI) | MIT | GitHub repo metadata |
| vercel-labs/agent-skills | **not verified** — root LICENSE raw 404, no License metadata | raw fetch |
| vercel-labs/agent-browser | Apache-2.0 © 2025 Vercel Inc. | raw LICENSE |
| leonxlnx/taste-skill | MIT © 2026 Leonxlnx | raw LICENSE |
| pbakaus/impeccable | Apache-2.0 © 2025 Paul Bakaus | raw LICENSE |
| coreyhaines31/marketingskills | MIT © 2025 Corey Haines | raw LICENSE |
| dietrichgebert/ponytail | MIT © 2026 DietrichGebert | raw LICENSE (matches credit line already in kit `skills/ponytail/SKILL.md`) |
| supabase/agent-skills | MIT © 2026 Supabase | raw LICENSE |
| nextlevelbuilder/ui-ux-pro-max-skill | MIT © 2024 Next Level Builder | raw LICENSE |
| browser-use/browser-use | MIT © 2024 Gregor Zunic | raw LICENSE |
| shadcn-ui/ui | not fetched (no disposition depends on it) | — |

## 3. Official-sources findings (exact source, fetched 2026-09-06)

### 3.1 openai/skills is deprecated — follow openai/plugins + build guides

`github.com/openai/skills` README, verbatim banner: "**This repository is
deprecated.** For current Codex skill and plugin examples, use the [OpenAI
Plugins repository](https://github.com/openai/plugins). If you want to add your
own skills to Codex, follow the [Build plugins](https://developers.openai.com/codex/plugins/build)
guide, which includes instructions for creating a skill-only plugin."
The README's `$skill-installer` flow therefore must not be recommended
blindly; current primary sources are `developers.openai.com/plugins/build/skills`
and `/plugins/build/plugins` (both fetched).

Current official skill structure (from /plugins/build/skills): `SKILL.md` with
`name`+`description` frontmatter ("The description determines when the model
considers the skill"); `references/`, `assets/`, `scripts/` for supporting
material; optional `agents/openai.yaml` declaring MCP tool dependencies;
"Prefer one focused skill over a large collection of loosely related
instructions. Split workflows when they have different triggers, inputs, or
success criteria." Test guidance: five request classes — direct, indirect,
incomplete-input, should-not-activate, edge case.

Plugin packaging (from /plugins/build/plugins): required
`.codex-plugin/plugin.json` (`name`, `version`, `description`, `"skills":
"./skills/"`); marketplaces are JSON catalogs at
`$REPO_ROOT/.agents/plugins/marketplace.json` or `~/.agents/plugins/marketplace.json`;
entries need `policy.installation` (AVAILABLE | INSTALLED_BY_DEFAULT |
NOT_AVAILABLE), `policy.authentication` (ON_INSTALL | ON_USE), `category`.
Note for any future kit distribution decision: this is the current official
Codex-side packaging path; copying text from openai/plugins itself is unsafe
(no license found) — structure and docs are the citable sources.

### 3.2 GPT-6 Astra latest-model guide (developers.openai.com/api/docs/guides/latest-model)

Full guide read. Behavior/prompting facts relevant to the kit (all quotes
verbatim from the guide):

- **Initiative and follow-through**: Astra "is more likely to ask for
  clarification where earlier models would make assumptions"; recommended
  prompt: "You should infer the user's intent and task scope ... bias towards
  action and carry the user's intended task to completion." Approval should be
  requested "only after preparing a concrete, reviewable result"; "Do not
  introduce unsolicited warnings, disclaimers, approval flows, or
  safety/compliance checklists due to hypothetical risk."
- **Instruction following / user intent precedence**: Astra "can be more
  sensitive to instructions contained in skills and other files, such as
  AGENTS.md. We **strongly recommend** auditing skills and other files";
  recommended prompt: "The user's instructions take precedence over guidelines
  provided in a skill." Diagnostic prompt: "If a skill causes you to ask for
  permission or confirmation, pause, leave requested work unfinished, or
  diverge from the user's intent, name and link to the exact SKILL.md file you
  read, quote the relevant instruction, and briefly explain how it applies.
  Distinguish explicit skill requirements from your interpretation of
  guidelines."
- **Calibrated testing/verification**: "For coding tasks, the model tends to be
  thorough in testing before considering a task complete. For smaller tasks,
  this can result in broader tests than the task requires." Recommended prompt:
  "Do not write tests for reversible, low-impact changes that mirror the
  implementation. ... Run tests appropriate to the change and complete required
  checks. Once those pass, broaden or repeat testing only when new changes,
  failures, or unresolved concerns justify it; otherwise, continue toward
  completing the task."
- **Subagent delegation**: "The model may delegate less often than desired for
  your workflow. Specify when and how much it should use subagents for parallel
  work." Recommended prompt: "If at any point you can parallelize work by
  delegating tasks to another agent (no matter if you are the root or
  subagent), you should do so using collaboration tools if it could save time
  or improve quality."
- Also: prose-style and slop-word-blocklist prompts; async tool calling,
  mid-turn steering, `configuration_update` reasoning-effort changes; no
  `none` reasoning effort; `temperature`/`top_p`/`top_logprobs` removed.

### 3.3 pvncher X article — via fxtwitter **mirror**, corroborated (§1)

"Rethinking skills and prompts for GPT-6 Astra" (2026-09-04). Key claims, all
taken from the mirror payload, never read on x.com itself:

- Over-installing skills is a mistake: descriptions load into context; "when
  you add too many skills, Codex starts shortening their descriptions to fit.
  The model ends up seeing less of each description." Descriptions with "pick
  me" energy or contradictions cause wrong-skill loading.
- Updated `$skill-creator` guidance (mirrors §3.1/§4.3): descriptions "as short
  as possible while making it clear when the model should use them";
  progressive disclosure — "make the root document a minimal router that points
  to supporting docs and scripts"; avoid "elaborate itineraries or recipes" —
  "overly specific guidance can now hinder results where it previously helped";
  repo skills serve other contributors' agents on different models, so avoid
  overconstraining stronger models.
- AGENTS.md: "revisit each instruction and ask whether the task still needs
  it"; forcing repo-map/doc stacks before every edit "is excessive for a typo
  fix"; "Previous models needed encouragement to run tests and check their
  work. GPT-6 Astra does that on its own, so the same instructions can lead to
  unnecessary testing."
- Persistence: Astra "can feel more tentative about when to stop. It may reach
  a first implementation and come back for your review while there's still work
  to do" → "define completion before starting"; a stop-for-review requirement
  "will pull the model toward an earlier stopping point."
- Decision boundaries: legacy "ask first" language from weaker-model days can
  make Astra "stop work where you'd actually be happy for it to continue";
  grant scoped permissions (example blockquote: local disposable-fixture tests
  may be run/fixed/rerun "without asking for approval at each step").

These point the same way as the kit's own measurement (DeepSWE +41% prompt
tokens on identical outcomes, `docs/research/2026-09-05-open-source-product-direction.md`
§1.1) and as the product-evidence workstream's bounded instruction correction.

## 4. Candidate patterns inspected (hypotheses, not approved skills)

Nothing here is an instruction to create a skill. Each is a hypothesis for the
director to accept or drop; adoption would still need the kit's own trigger test
and skill-authoring rules. All four are mattpocock/skills (MIT, §2), fetched
verbatim today.

### 4.1 handoff (`skills/productivity/handoff/SKILL.md`) — adapt hypothesis

Upstream body is five short paragraphs: user-invoked (`disable-model-invocation:
true`, `argument-hint`); writes the handoff doc to the OS temp dir rather than
the workspace; includes a "suggested skills" section; "Do not duplicate content
already captured in other artifacts (specs, plans, ADRs, issues, commits,
diffs). Reference them by path or URL instead"; redacts secrets/PII; tailors to
the argument. Kit gap: dev-wiki is long-term memory; nothing covers
session→session handoff. Pure prompt, so it fits kit constitution.
Adaptation notes: `argument-hint`/`disable-model-invocation` are Claude/Codex
frontmatter fields, not in the kit's Hermes frontmatter contract — express as
body text ("invoke explicitly; do not auto-trigger"); temp-dir choice conflicts
with kit convention of repo docs — decide per kit norms during adaptation.

### 4.2 domain-modeling (`skills/engineering/domain-modeling/SKILL.md`) — adapt hypothesis

Discipline: challenge terms against `CONTEXT.md` glossary, sharpen fuzzy
language, stress-test with concrete scenarios, cross-reference claims against
code, update glossary inline ("Don't batch these up"), ADR only when all three
hold: hard to reverse + surprising without context + real trade-off. Uses
progressive disclosure: `CONTEXT-FORMAT.md`, `ADR-FORMAT.md` side files;
`CONTEXT-MAP.md` for multi-context repos; files created lazily. Kit gap:
no repo-shared ubiquitous-language artifact (dev-wiki memory is personal,
CONTRIBUTING rule 6). "CONTEXT.md is a glossary and nothing else" is a clean
boundary the kit lacks. MIT-licensed, so adaptable if the director pursues it.

### 4.3 research (`skills/engineering/research/SKILL.md`) — adapt hypothesis (merge, not new skill)

Upstream body is short: spin up a **background agent**; investigate against
**primary sources** ("Follow every claim back to the source that owns it");
write findings to a single Markdown file citing each claim's source; save where
the repo keeps such notes, match existing convention. Kit's web-research covers
the protocol but is answer-oriented (respond + "offer to save"); the additive
patterns are (a) delegate the reading legwork to a background agent, (b) land
findings as a cited repo doc by convention — this very document is an instance.
If pursued, merging into web-research beats adding a skill (thin kit) — hypothesis, not decided.

### 4.4 wayfinder (`skills/engineering/wayfinder/SKILL.md`) — adapt hypothesis (heaviest)

Multi-session planning as a "shared map": one tracker issue labeled
`wayfinder:map` holding Destination / Notes / Decisions-so-far (index of
one-line gists linking closed tickets) / Not-yet-specified ("fog of war") /
Out-of-scope; child tickets are **decision** questions (types: research=AFK,
prototype=HITL, grilling=HITL, task) sized to one ~100K-token session; claim by
assignment; native blocking edges; frontier = open+unblocked+unclaimed; one
ticket per session (research excepted); fog graduates into tickets only when a
question becomes precisely statable; "Plan, don't do". Kit gap: writing-plans
is single-session; dispatching-parallel-agents has no persistent cross-session
decision map. Adaptation cost is real: upstream depends on a tracker configured
by `setup-matt-pocock-skills`; kit would default to the local-markdown tracker
(upstream itself names this fallback). Also longest body of the four — would
need router+references split per §3.1 and §4.5 if adopted.

### 4.5 Official skill-creators (reference for skill-authoring upkeep)

- openai `.system/skill-creator` (Apache-2.0 LICENSE.txt fetched; repo is
  deprecated, but this is the `$skill-creator` the Astra article references):
  "The context window is a public good"; "Only add context Codex doesn't already
  have"; degrees-of-freedom dial (high = text heuristics, medium = parameterized
  scripts, low = exact scripts for fragile ops); three-level loading (metadata
  ~100 words / body <5k words / bundled resources); SKILL.md <500 lines;
  references one level deep; TOC above 100 lines; **no README/CHANGELOG/INSTALL
  inside a skill folder**; scripts only for repeated or deterministic code.
- anthropics `skill-creator` (Apache-2.0 fetched): an eval loop the kit's
  skill-authoring lacks — draft → 2-3 realistic prompts → with-skill AND
  baseline runs spawned in one turn → `timing.json` from task notifications →
  graded assertions → aggregated benchmark → human review → iterate, plus a
  description-improver pass. The machinery (viewer server, benchmark scripts)
  would collide with "no new runtime" if bundled wholesale; the kit's `eval/`
  harness could host an equivalent if ever prioritized.

## 5. Disposition — all 50 workbook rows

Full 50-row table (skill/repo, per-row license status, kit relation, disposition with reason) is split into `2026-09-06-priority-skill-sources-inventory.md` (main document hit the 300-line limit). Counts from that file, which defines the vocabulary (`adopted` requires footer/LICENSE provenance; `defer` means no present measured need, NOT that the domain is out of the kit's possible scope):

- **adopted (real import provenance): 5** — rows 27, 32, 33, 37 (kit footers "Source: obra/superpowers (MIT)") + 49 (kit ponytail Credits names upstream).
- **overlap (functional coverage only): 13** — rows 2, 4, 6, 10, 15, 16, 17, 18, 22, 23, 24, 35, 38. Row 38 (subagent-driven-development) sits here, not under `adopted`: kit LICENSE lists it among upstream-derived provenance but no kit folder of that name exists, so exact adoption is not demonstrable.
- **overlap, partial and unverified: 1** — row 43 (webapp-testing): kit Verify rules require browser verification for web UI changes, but no side-by-side comparison with the upstream procedure was performed.
- **adapt hypotheses: 4** — row 8 handoff (§4.1), row 14 domain-modeling (§4.2), row 19 wayfinder (§4.4), row 21 research merged into web-research (§4.3). Plus row 26 pattern-mine only (§4.5), row 3 adapt-idea only.
- **reject — license: 4** — rows 34, 40, 41, 42 (all four LICENSE.txt fetched; identical proprietary text).
- **reject — kit constitution (CONTRIBUTING rule 4): 3** — rows 1, 44, 46.
- **defer (no present measured need): 18** — rows 5, 7, 9, 11, 12, 13, 20, 25, 28, 29, 30, 31, 36, 39, 45, 47, 48, 50. Rows 11-12 also carry an unresolved-license blocker; rows 7 and 31 note that the existence of harness browser/vision tooling does not establish that a procedural skill would be redundant — that equivalence was never tested.

## 6. Recommendations (for the director; no edits made here)

1. **Instruction-level corrections come from §3, not from the workbook.** The
   Astra guide + pvncher article support exactly the bounded correction
   product-evidence is already making (user-intent precedence, skill-pause
   diagnostics, calibrated verification, delegation tuning, persistence /
   completion-defined-up-front). Do not resurrect blanket always-test or blanket
   approval-gate language; do not bulk-import skills (§3.3).
2. **Skill-content hypotheses, cost/benefit order — each needs a director
   decision, none is automatic, and the kit's trigger test applies:** (a) handoff
   (§4.1 — small, clean gap); (b) domain-modeling (§4.2 — CONTEXT.md/ADR
   discipline, repo-shareable, complements personal dev-wiki); (c) research
   merged into web-research (§4.3 — one paragraph, no new skill); (d) wayfinder
   only if multi-session decision-map demand is measured (§4.4 — largest cost;
   needs local-markdown tracker default and router/references split).
3. **skill-authoring upkeep:** cite §3.1 structure rules and §4.5 patterns
   (degrees-of-freedom dial, no-aux-files-in-skill-folder, references one level
   deep, five test-request classes) when next revising; both source skills are
   Apache-2.0 with LICENSE.txt fetched — attribution required on any copied text.
   openai/plugins text: reference structure only (no license found).
4. **Distribution note (future, not now):** if the kit ever ships as a Codex
   plugin, the current official path is `.codex-plugin/plugin.json` +
   `.agents/plugins/marketplace.json` per /plugins/build/plugins (§3.1); the
   deprecated openai/skills `$skill-installer` flow must not be recommended.

## 7. Unverified / caveats

- Workbook install counts are skills.sh marketing, unverified; star counts are
  stale versus the GitHub values fetched today (§2). Neither is a quality signal.
- x.com direct read blocked. The article body came from the fxtwitter **mirror**
  (`https://api.fxtwitter.com/pvncher/status/2095991462416490862`), full payload
  preserved at `artifact://135`; search results were secondary retellings only
  (§1). Author/date/title/substance agree across sources, but x.com itself was
  never read. No engagement counts are used as evidence anywhere in this document.
- vercel-labs/agent-skills license unresolved (root LICENSE 404); rows 11-12 are
  deferred with that blocker stated as unresolved, not resolved.
- anthropics per-skill licenses fetched for `skill-creator` (Apache-2.0) and for
  `docx`/`pdf`/`pptx`/`xlsx` (all four individually; identical proprietary text).
  Not fetched: rows 5, 43, 45, 47, 48 — scope-based dispositions; fetch that
  skill's LICENSE.txt before any future pursuit.
- api.github.com returned 403 once (rate limit); no fact here depends solely on it.
