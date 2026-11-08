---
name: skill-authoring
description: 'Use when creating or editing a skill, or turning a session, procedure or URL into a reusable one ("learn", "/learn", "turn this session into a skill", "make a skill from this workflow", "сделай скилл из этой процедуры", "навык из"): name and description rules, folder layout, script bundling, promotion and retirement evidence. Not for saving conclusions in memory (dev-wiki) or for ordinary code changes.'
license: MIT
compatibility: applies to skills/ in this set, ~/.hermes/skills, .claude/skills
metadata:
  version: "6.1.0"
---

# Authoring skills

## 1. Frontmatter

| Field | Rule |
|---|---|
| `name` | Required. 1–64 chars, `a-z0-9` and hyphens, no leading/trailing or doubled hyphen, must equal the folder name |
| `description` | Required. 1–1024 chars. Triggers + boundary, keyword-rich, no workflow summary: `Use when [triggers]. Not for [neighbor] (use [other-skill]).` |
| `metadata` | Optional `str → str` map; kit convention `version` as a plain string, unbumped on a text edit |
| `license`, `compatibility` | Optional; `compatibility` 1–500 chars, only for real environment requirements |

The description is the only text a future session sees before deciding: triggers
(the words users type, in their language, including "сделай скилл" and symptoms)
plus one clause naming the neighbor it is confused with. A trigger miss is fixed with
the phrasing the user used.

## 2. Layout and scripts

`SKILL.md` required; `scripts/` helpers; `references/` detail behind a "read when"
pointer; `evals/evals.json` expected; `assets/` optional. References one level deep —
chained ones force multi-hop loads.

A bundled script prefers an existing tool (`npx`, `uvx`, `pipx`, `bunx`), documents
dependencies in SKILL.md or `compatibility`, and is agent-safe: no interactive
prompts and arguments only, since an agent waits on a TTY forever; `--help` and
errors saying what to do next; stdout result, stderr diagnostics, exit code carrying
success; idempotent with `--dry-run` for destructive steps; output bounded to
10–30K characters, where agents truncate. Run it via `--help`, not its source.

## 3. Body: size and tone

- **Small.** Each loaded procedure costs context and work; assess that cost
  against the outcome it protects. Stay well under 500 lines; past ~350, move
  detail into `references/<topic>.md`.
- **Each rule lives once**: restating OPS or a neighbor skill dilutes what is unique
  here. "Use X when Y, because Z" beats "critical, you must"; MUST/NEVER is for
  safety, authority and fabrication lines.
- **Keep decision-relevant examples**: retain a table when it prevents a named
  failure, not merely because it increases compliance. Tables and prose carry
  the same burden of demonstrating value in their intended scope.
- **Write what the agent doesn't know**: gotchas, exact commands, fields,
  thresholds. Positive recipes beat prohibitions for output shape.

## 4. Merge before you add

Overlapping triggers split routing and weaken both: extend the owner with a headed
section, bulk to its `references/`. Merging X into Y folds X's body and its
`evals/evals.json` cases in with their `should_trigger` semantics, adds a near-miss
negative owned by a neighbor, then deletes X. A new skill needs a distinct job:
another artifact, workflow moment or trigger phrase.

## 5. Turning a session into a skill

Raw material: this chat, or a named directory, procedure or URL — not a conclusion
to remember (dev-wiki).

1. **Isolate the repeatable procedure**: what a fresh session would rediscover, in
   order, with the why behind non-obvious decisions.
2. **Trigger test before writing**; no plausible trigger, stop. Cases in
   `skills/<name>/evals/evals.json`: `{"skill_name": "<name>", "evals": [...]}` of
   `id`, `prompt`, `should_trigger` — one natural request true, one neighbor's near
   miss false.
3. **Draft the body** by §3.
4. **Location**: portable → kit `skills/<slug>/` under the English, file-size and
   review checks; machine-specific → the harness's own user skills dir, which does
   not travel. Publishing it is an OPS §1 action.
5. **Ship it as a candidate** until §6's evidence exists.

## 6. Promotion and retirement evidence

Run the tools, don't argue from impressions; without `--executor` they only validate
inputs (dry run).

- `python eval/trigger_eval.py --queries auto --only <slug>` — trigger and false
  rate; `auto` reads the skill's `evals/evals.json`, else `eval/trigger_queries.json`;
  `--executor "docker:<image> <argv>"`/`--model` run it live.
- `python eval/runner.py --scenario <name> --repeat <n>` — behavior on the
  originating scenario; `eval/scenarios`; `--executor`/`--judge` grade it,
  `--release-grade` when it counts.
- `python eval/ablate.py --executor "docker:<image> <argv>"` — pass-rate change per
  skill removed, on its scenarios.
- `python scripts/tools/usage_audit.py --retirement-report` — no observed read
  requests in the window (default 14 days), proposal only.

Addition and continued default use of an optional procedure need a named user
outcome or failure it protects, plus evidence proportionate to its cost and risk.
Routing checks show whether it is selected, not whether it helps. Use an originating
case, a nearby negative and a held-out case to assess outcome, side effects and
additional work; do not promote on compliance or trigger rate alone.

Apply the same standard to removal or narrowing: it need not make the model smarter.
A reversible trial can be justified by observed cost and weak benefit evidence,
with checks for the specific regressions at risk. Lack of a detected benefit is
uncertainty, not proof of uselessness; retain unique useful knowledge on demand
where appropriate. Read counts alone justify neither keeping nor retiring a skill.

Authority, stopping, honesty and protections for irreversible or high-impact
actions are not optional workflow overhead. Do not remove them by this cost rule.
Keep the evidence and limitations attached to the decision; no requirement for
another global benchmark, gate or fixed report format.

## Gotchas

- Over-generalizing: encode the procedure that exists, not the class it resembles.
- Russian only in trigger words inside the description; bodies stay English.
- Scripts live in `scripts/`, never inline in the body; a skill that was wrong once
  is fixed like code — edit it, re-run the case that caught it.