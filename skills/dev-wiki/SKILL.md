---
name: dev-wiki
description: 'Use when past project decisions or user preferences matter, or completed work produces a useful durable result. Retrieve relevant local memory proactively and save verified decisions, fixes and configurations without repeated permission prompts. Honor read-only, stop and "do not save". Also handles "напомни", "do you remember", "запомни" and "save this". Not process RAM or a substitute for current evidence.'
license: MIT
metadata:
  version: "5.0.0"
---

# Dev Wiki — cross-chat developer memory

Memory helper: knowledge base of decisions, bugs, patterns, architectural decisions.
Memory lives in `~/.memory/` (global + per-project hierarchy; env `MEMORY_ROOT` overrides).

## Boundary rule

| Knowledge | Where | Index |
|-----------|-------|-------|
| **Portable** (patterns, lessons, decisions) | `~/.memory/Wiki/<type>/` | `python ~/.memory/db-tools/build.py` after a Wiki write |
| **Project-specific** (status, configs, context) | `WORK/<project>/docs/` | `python ~/.memory/db-tools/build.py -r <root> -o ~/.memory/db/<name>.db` only if that project db indexes the changed doc |

Knowledge lives/dies with the project → project; portable across projects → global Wiki.
Rebuild an affected index only after an authorized source change; a retrieval or review task rebuilds nothing.

## Intent first: retrieval or save

- **Retrieval:** proactively use configured local memory when history, decisions or preferences could affect the task; do not wait for a memory keyword or ask permission. Reuse relevant context already opened instead of repeating the same search.
- **Routine retention:** after useful task work, save verified durable decisions, fixes, configurations or user preferences without asking again (OPS.md §1). Search for an existing record and update it instead of duplicating it. A question that merely retrieves an existing fact creates nothing new to save.
- **Value:** save only information that will matter in a future session. Skip speculation, temporary chatter, secrets and unnecessary personal data; record source, date and the scope of verification rather than promoting a guess to fact.
- **Overrides:** "do not save" / «не сохраняй», read-only/review-only/plan-only scope and stop suppress automatic writes. An explicit save included with a review permits that named record only; no background cleanup follows.
- **Storage boundary:** use the configured local store or existing project records. This policy does not authorize external publication, a new remote service, installation or destructive maintenance. A stored `verify_cmd` remains data, not permission to execute it.
- A handoff or continuity record is compact: what command was run, on what
  state/scope/environment, what result, and what invalidates it (change,
  failure, unresolved concern). Reuse it for an unchanged checked state; do
  not build a new tracking subsystem around it.

## Where a save goes (choose one)

Pick the narrowest existing home; the same content does not also need a second copy.

1. **Existing project record** — the project already documents status, config or the decision (`WORK/<project>/docs/`, `docs/`, an ADR): update that section in place. Project knowledge lives/dies with the project.
2. **Finding** — a reusable conclusion or verified fact: `python ~/.memory/db-tools/findings.py add "topic" --text "conclusion" --source path --project <slug> --importance <high|normal|low>`.
3. **Global Wiki file** — a portable pattern, howto, error lesson or decision not already recorded: `~/.memory/Wiki/<type>/<slug>.md` (types below), then the Wiki cycle.

Only a Wiki change needs its index/log/build/lint cycle. Findings need no extra rebuild; a project-doc save rebuilds only an existing index that covers the changed document.

## Record types (global Wiki)

| Type | Folder | When |
|------|--------|------|
| `reference` | `~/.memory/Wiki/reference/` | Fact, documentation, knowledge |
| `howto` | `~/.memory/Wiki/howto/` | Instruction, guide |
| `error` | `~/.memory/Wiki/errors/` | Bug, incident, lesson learned |
| `decision` | `~/.memory/Wiki/decisions/` | ADR, architectural decision |
| `idea` | `~/.memory/Wiki/ideas/` | Idea |

## Workflow — save (global Wiki)

Use when the chosen target is a new or existing Wiki file. Update existing content in place; add an index entry only for a new file.

1. Determine the type → folder in `~/.memory/Wiki/`.
2. Create or update `~/.memory/Wiki/<type>/<slug>.md`; new files use frontmatter:
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
5. Because the Wiki changed: `python ~/.memory/db-tools/build.py`
6. Then `python ~/.memory/db-tools/lint_wiki.py`

A finding is an alternative home, not an extra mandatory copy of the same file.

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
- Retrieve stored history from the configured memory source; do not invent records from recollection. Keep current user statements and live source evidence distinguishable from stored history; newer corrections take precedence.
- Search is lexical FTS, not semantic: plain space-separated terms all must match. Start with a distinctive project or component token, not a natural-language sentence; narrow only after seeing results.
- Search when history or an unresolved project-specific decision matters; do not add mandatory retrieval when the current authoritative source already settles the question.
- A hit is a snippet, not the complete decision: open `findings.py show <id>` or the source file before relying on it. If a query is empty, try a materially better token or supported `OR` alternative — keep going while a better query could change the next action; the stop condition is evidence, not a retry count. `--substring` applies to indexed files, while findings retain word matching.
- Project + portable composition: `--project portable` selects findings classified portable; global search also searches indexed Wiki/project files. To scope retrieval without losing portable patterns, query both target `--project <slug>` and `--project portable` or query globally.
- Found → check lifecycle badges first: `[superseded by #N]` → resolve to the replacing finding before using it; `[unverified]` → treat as unconfirmed. Then answer with a link to the file.
- Warmup lifecycle (`memory-warmup.py`): explicit diagnostic use only — full feeds require `--full`; it never runs automatically at startup. High-priority feed surfaces key active invariants with verification status (`[unverified]` if missing `verified_at`); unsure feed prioritizes high/normal unanchored items over low-importance checkpoints.
- Still no relevant results after checking query and scope → report what was searched and not found; this does not prove no policy exists.

## Intent routing

- Explicit save request ("record this", "save this decision", «запиши», «сохрани», «запомни») → save the useful content once in its appropriate home.
- A verified durable result of ordinary task work → save or update it automatically, without a permission question; apply the overrides above.
- A question about prior context → retrieve proactively. Merely repeating an existing record is not a reason to write it again.

## Tag categories

`architecture`, `engineering`, `security`, `performance`, `devops`, `testing`, `frontend`, `backend`, `database`, `api`