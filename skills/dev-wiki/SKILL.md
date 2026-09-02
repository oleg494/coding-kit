---
name: dev-wiki
description: 'Always-on. Cross-chat memory (database, not conversation): record decisions, errors, patterns in the global Wiki (~/.memory). Use on "record"/"save"/"remember"/"запиши"/"сохрани"/"запомни"/"в память"/"память" or "what do we know about X"/"напомни". Hierarchy: portable → ~/.memory/Wiki/; project-specific → WORK/<project>/docs/. Cycle: file → index.md → log.md → python ~/.memory/db-tools/build.py → lint.'
metadata:
  version: "4.0.2"
---

# Dev Wiki — cross-chat developer memory

Always-on skill. Knowledge base: decisions, bugs, patterns, architectural decisions.
Memory lives in `~/.memory/` (global + per-project hierarchy; env `MEMORY_ROOT` overrides).

## Boundary rule

| Knowledge | Where | Index |
|-----------|-------|-------|
| **Portable** (patterns, lessons, decisions) | `~/.memory/Wiki/<type>/` | `python ~/.memory/db-tools/build.py` |
| **Project-specific** (status, configs, context) | `WORK/<project>/docs/` | `python ~/.memory/db-tools/build.py -r <root> -o ~/.memory/db/<name>.db` |

Knowledge lives/dies with the project → project; portable across projects → global Wiki.

## Save reflex (proactive, not only on request)

- **On every finished task / made decision / closed bug** — 10-second check:
  would a future session need this? Yes → save. No → skip (noise-free is deliberate).
- Conclusions → `findings.py add`; portable patterns → Wiki; realizations by trigger below.

## Record types (global Wiki)

| Type | Folder | When |
|------|--------|------|
| `reference` | `~/.memory/Wiki/reference/` | Fact, documentation, knowledge |
| `howto` | `~/.memory/Wiki/howto/` | Instruction, guide |
| `error` | `~/.memory/Wiki/errors/` | Bug, incident, lesson learned |
| `decision` | `~/.memory/Wiki/decisions/` | ADR, architectural decision |
| `idea` | `~/.memory/Wiki/ideas/` | Idea |

## Workflow — save (global)

1. Determine the type → folder in `~/.memory/Wiki/`.
2. Create file `~/.memory/Wiki/<type>/<slug>.md` with frontmatter:
   ```yaml
   ---
   type: reference
   title: "Title"
   description: "About what"
   date: 2026-08-15
   tags: [category, topic]
   ---
   ```
3. Update `~/.memory/Wiki/index.md`.
4. Append to `~/.memory/Wiki/log.md`.
5. `python ~/.memory/db-tools/build.py`
6. `python ~/.memory/db-tools/lint_wiki.py`
7. Important conclusion → `python ~/.memory/db-tools/findings.py add "topic" --text "conclusion" --source path`

## Workflow — search

```bash
python ~/.memory/db-tools/search_all.py "query"          # all databases at once
python ~/.memory/db-tools/search_all.py "query" --substring   # declensions/substrings
```

- Search the database, NOT conversation memory.
- Found → answer with a link to the file.
- Not found → "not in the database".

## Auto-write triggers

- "record", "save", "remember", «запиши», «сохрани», «запомни», «в память», «память» → full cycle.
- Bug/incident → `~/.memory/Wiki/errors/`.
- Architectural decision → `~/.memory/Wiki/decisions/`.
- New pattern → `~/.memory/Wiki/reference/`.

## Tag categories

`architecture`, `engineering`, `security`, `performance`, `devops`, `testing`, `frontend`, `backend`, `database`, `api`