---
name: skill-authoring
description: 'Use when creating or editing any skill: frontmatter rules (name/description), folder structure, script bundling, quality checklist — including converting the current session/procedure/URL into a new reusable skill ("learn", "/learn", "turn this session into a skill", "make a skill from this workflow", "сделай скилл из этой процедуры", "навык из"). Per the Agent Skills specification (Hermes-compatible).'
compatibility: applies to skills/ in this set, ~/.hermes/skills, .claude/skills
---

# How to author skills correctly

A set of rules based on the Agent Skills specification + practice. Verified against real skills.

## 1. Frontmatter (required fields)

```markdown
---
name: my-skill
description: Use when [triggers/symptoms/contexts]. [what it does + when to apply]
---
```

| Field | Rule |
|---|---|
| `name` | REQUIRED. 1–64 characters, `a-z0-9` + hyphens. **Must match the skill's folder name** |
| `description` | REQUIRED. 1–1024 characters. «What it does + when to use»; include the keywords the agent searches by. NOT a workflow summary |
| `license` | optional |
| `compatibility` | 1–500 characters, only if there are environment requirements |

## 2. Directory structure

```
skill-name/
├── SKILL.md            # required
├── scripts/            # optional: executable scripts
├── references/         # optional: details, «read when X»
├── assets/             # optional
└── any other files/folders — allowed
```

- From SKILL.md reference files with **relative paths from the skill root**.
- Progressive disclosure: SKILL.md < ~500 lines; details go into `references/` with a pointer «read this when X happens».

## 3. Script bundling (scripts/)

1. **First check for an existing tool**: `npx`, `uvx`, `pipx`, `bunx` — take an existing one, write your own only when none exists.
2. If you bundle a script, it must be **self-contained**: document dependencies in SKILL.md or `compatibility`.
3. **Agent-safe design:**
   - NO interactive prompts — the agent will hang on a TTY. Input only via arguments.
   - `--help` with usage; clear error messages.
   - Structured output: result to stdout, diagnostics to stderr.
   - Idempotency; `--dry-run` for destructive operations.
   - Predictable output size (agents truncate ~10–30K characters).

## 4. Best practices and antipatterns

**Do:**
- Small, composable, like a function: one coherent task.
- Description in the imperative: «Use when …», list the triggers. Agents under-trigger.
- Add what the agent does not know; drop what it already can do.
- `Gotchas` sections — the most valuable content; checklists for multi-step processes; output templates.
- Defaults, not menus; procedures, not declarations; explain «why».
- Calibrate detail to fragility: for fragile operations — prescriptively.

**Do not:**
- Do not stuff code into SKILL.md — move it to `scripts/`.
- Do not describe the workflow in `description`.
- Do not give many equal options without a default.
- Do not generate generic content without subject knowledge.

## 5. New skill template

```markdown
---
name: my-skill
description: Use when [symptoms/contexts]. [what it does + when to apply, 1–1024 chars.]
license: MIT               # optional
compatibility: Requires X  # optional
---
# What it does (1–2 sentences)

## When to use / when NOT to use
## Workflow (numbered, imperative)
## Gotchas
## Available scripts (relative paths from the skill root)
## References (pointers «read when X»)
```

## 6. Turning a session into a skill (the former /learn flow)

The raw material is what happened in this chat (or a named directory/procedure/URL) — not a skill-format question, and not a conclusion to remember (that is dev-wiki/findings).

1. **Isolate the repeatable procedure.** What did you actually do that a fresh session would have to rediscover? Steps in order, with the "why" behind non-obvious decisions. One-off facts are NOT skills → memory instead; general knowledge the agent already has is NOT a skill (YAGNI).
2. **Trigger test before writing.** In a fresh session, would the description fire for the natural phrase a user would say? No plausible trigger → stop, don't write it. The description is the only thing a future session sees.
3. **Draft SKILL.md** by the rules above: numbered imperative procedure, defaults (not menus), gotchas — the most valuable section.
4. **Choose the location.** Portable (any machine/project) → kit `skills/<slug>/`, commit — subject to the kit gates (English, file-size, review), propagates to every harness automatically. Machine/user-specific → the harness's user skills dir (e.g. `~/.claude/skills/`); does NOT propagate.
5. **Verify before claiming done.** Frontmatter delimiters, `name` == folder, description within limits; trigger test against the most natural phrase; replay one real past case through the new skill — same outcome, ideally fewer wasted moves.

Gotchas: don't over-generalize — encode the procedure that exists, not the class of procedures; Russian belongs only in trigger words; scripts stay in `scripts/`, never inline; a skill that was wrong once is fixed like code — edit + verify against the same case.