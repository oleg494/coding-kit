---
name: dev-wiki
description: 'Always-on. Cross-chat memory (database, not conversation): record decisions, errors, patterns in the global Wiki (~/.memory). Use on "record"/"save"/"remember"/"запиши"/"сохрани"/"запомни"/"в память"/"память" or "what do we know about X"/"напомни". Hierarchy: portable → ~/.memory/Wiki/; project-specific → WORK/<project>/docs/. Cycle: file → index.md → log.md → python ~/.memory/db-tools/build.py → lint.'
license: MIT
metadata:
  version: "4.4.0"
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

## Save reflex (bounded by task effect boundary)

- **Side-effect boundary:** read-only or review-only tasks produce NO memory writes unless explicitly requested by the user.
- **On every finished mutation task / made decision / closed bug** — 10-second check:
  would a future session need this? Yes → save. No → skip (noise-free is deliberate).
- Conclusions → `findings.py add`; portable patterns → Wiki; realizations by trigger below. Any saved `verify_cmd` is a proposed check, not standing authorization.
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
7. Important conclusion → `python ~/.memory/db-tools/findings.py add "topic" --text "conclusion" --source path --project <slug> --importance <high|normal|low>`

### Project Taxonomy & Importance

- **Projects:** dynamically discovered from `~/.memory/db/*.db` plus optional `projects.json`. Slug format: `[a-z0-9][a-z0-9_-]{0,63}`.
  - `portable`: cross-project reusable techniques, tools, and methodologies.
  - `unknown`: unclassified personal notes, coursework, or items not tied to a specific project.
- **Importance levels:**
  - `high`: critical security boundaries, invariants, data-loss prevention, and durable architectural contracts.
  - `normal`: standard actionable engineering findings, reproducible runbooks, feature setups, and telemetry.
  - `low`: transient checkpoints, scratch notes, personal experiments, or milestone logs.
  - `unreviewed`: default state prior to qualitative review.
- **Edit finding:**
  ```bash
  python ~/.memory/db-tools/findings.py edit <id> --project <slug> --importance <high|normal|low>
  ```
- **Batch classification:**
  ```bash
  python ~/.memory/db-tools/findings.py classify mapping.json --dry-run
  python ~/.memory/db-tools/findings.py classify mapping.json
  ```
  Mapping accepts a list or an object with `{"records": [...]}`:
  ```json
  [{"id": 1, "candidate_project": "coding-kit", "candidate_importance": "low", "project_rationale": "...", "importance_rationale": "..."}]
  ```
  Batch classification is atomic (rolls back on any error) and idempotent: user-curated records (manual edits with provenance `cli_edit`) are strictly preserved unless `--force` is supplied.

## Workflow — search

```bash
python ~/.memory/db-tools/search_all.py "query"                                        # all databases at once (project + portable)
python ~/.memory/db-tools/search_all.py "query" --project <slug> --importance high     # exact project scoped retrieval
python ~/.memory/db-tools/search_all.py "query" --project portable                    # portable cross-cutting retrieval
python ~/.memory/db-tools/search_all.py "query" --substring                           # declensions/substrings
```
- Search the database, NOT conversation memory.
- Project + portable composition: `--project portable` selects findings classified portable; global search also searches indexed Wiki/project files. To scope retrieval without losing portable patterns, query both target `--project <slug>` and `--project portable` or query globally.
- Found → check lifecycle badges first: `[superseded by #N]` → resolve to the replacing finding before using it; `[unverified]` → treat as unconfirmed. Then answer with a link to the file.
- Warmup lifecycle (`memory-warmup.py`): high-priority feed surfaces key active invariants with verification status (`[unverified]` if missing `verified_at`); unsure feed prioritizes high/normal unanchored items over low-importance checkpoints.
- Not found → "not in the database".
## Auto-write triggers

- "record", "save", "remember", «запиши», «сохрани», «запомни», «в память», «память» → full cycle.
- Bug/incident → `~/.memory/Wiki/errors/`.
- Architectural decision → `~/.memory/Wiki/decisions/`.
- New pattern → `~/.memory/Wiki/reference/`.

## Tag categories

`architecture`, `engineering`, `security`, `performance`, `devops`, `testing`, `frontend`, `backend`, `database`, `api`