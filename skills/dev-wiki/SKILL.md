---
name: dev-wiki
description: 'Use when prior decisions, project history or preferences could change the answer, or completed work left a durable result: "do you remember", "what did we decide", "save this", "напомни", "запомни", "сохрани". Retrieval with search_all.py and findings.py, plus deterministic save routing — project status to project docs, verified reusable conclusion to findings, portable how-to to the Wiki. Not for current code or fresh research.'
license: MIT
metadata:
  version: "6.0.0"
---

# Dev Wiki — cross-session developer memory

Memory root: `MEMORY_ROOT`, otherwise `~/.memory`. Each record has exactly one
home; a second copy adds drift, not redundancy.

## Precedence

- A read-only, review-only or plan-only scope, "do not save" / "не сохраняй",
  and stop suppress automatic saves. An explicit save request in that same
  turn is still honored for the named record only — no cleanup sweep follows.
- A newer correction supersedes the record it corrects.
- A retrieval- or review-only task rebuilds no index. Only an authorized
  source change refreshes the index that covers it.

## Routing: one home per record

| Content | Home | Index refresh |
|---|---|---|
| Project-specific status, config, or a decision this project already documents | the existing project doc (`docs/`, an ADR, `WORK/<project>/docs/`) — edit that section in place | only an index that already covers the changed doc |
| A verified, reusable conclusion about a problem or topic | findings store (`research.db`) | none |
| A portable how-to, reference, error lesson or decision | `~/.memory/Wiki/<type>/<slug>.md` | Wiki cycle below |

Default decision order: already documented by this project → project doc; a
conclusion with a source → finding; portable knowledge → Wiki file. Knowledge
that lives and dies with the project stays in the project; anything reusable
across projects goes to the global store.

## Save

**Finding** — search first, then update rather than duplicate:

```bash
python ~/.memory/db-tools/findings.py search "distinctive token"
python ~/.memory/db-tools/findings.py add "<topic>" --text "<conclusion>" --source <path or URL> --project <slug> --importance <high|normal|low>
python ~/.memory/db-tools/findings.py edit <id> --project <slug> --importance <level>
python ~/.memory/db-tools/findings.py show <id>
```

Add `--verify-cmd "<re-check command>"` when the conclusion can be re-checked
(`findings.py verify <id>` runs it), and `--supersedes <id>` when it replaces
older records.

**Wiki file** — new file or in-place update of `~/.memory/Wiki/<type>/<slug>.md`:

```yaml
---
type: reference
title: "Title"
description: "What it covers"
date: 2026-08-15
tags: [category, topic]
origin: web                             # web | session | subagent | manual
source_url: https://example.com/page    # required when origin is web
---
```

`origin` records where the content came from: `web` (fetched by read or browser), `session` (this conversation), `subagent` (delegated output) or `manual` (stated by the user). `origin: web` requires `source_url:`. `lint_wiki.py` checks both: a missing `origin` is a WARN (legacy notes predate the rule); `origin: web` without `source_url:` is an error and exits 1.

Then add the entry to `~/.memory/Wiki/index.md`, append a line to
`~/.memory/Wiki/log.md`, and complete the cycle:

```bash
python ~/.memory/db-tools/build.py
python ~/.memory/db-tools/lint_wiki.py   # exit 1 on errors; fix before reporting the save
```

**Project doc** — edit the existing section; rebuild only an index that already
indexes that document: `python ~/.memory/db-tools/build.py -r <root> -o ~/.memory/db/<name>.db`.

### Record types (global Wiki)

| Type | Folder | Content |
|---|---|---|
| `reference` | `Wiki/reference/` | Fact, documentation |
| `howto` | `Wiki/howto/` | Instruction, guide |
| `error` | `Wiki/errors/` | Bug, incident, lesson |
| `decision` | `Wiki/decisions/` | ADR, architectural decision |
| `idea` | `Wiki/ideas/` | Idea, not yet a decision |

### Findings metadata

Projects are discovered from `~/.memory/db/*.db` plus optional `projects.json`;
slug format `[a-z0-9][a-z0-9_-]{0,63}`. Reserved slugs: `portable` for
cross-project techniques and tools, `unknown` for notes not tied to a project.

Importance drives retrieval filters: `high` invariants, security boundaries and
data-loss prevention; `normal` actionable engineering findings, runbooks,
setups; `low` checkpoints and scratch notes; `unreviewed` the default before
review. Batch classification is atomic and idempotent, and preserves
user-curated records (`cli_edit` provenance) unless `--force` is passed:

```bash
python ~/.memory/db-tools/findings.py classify mapping.json --dry-run
python ~/.memory/db-tools/findings.py classify mapping.json
```

## Retrieve

```bash
python ~/.memory/db-tools/search_all.py "distinctive token"                    # every store at once
python ~/.memory/db-tools/search_all.py "token" --project <slug> --importance high
python ~/.memory/db-tools/search_all.py "token" --project portable             # reusable patterns only
python ~/.memory/db-tools/search_all.py "token" --substring                    # declensions, partial words
python ~/.memory/db-tools/search_all.py "token" --state current --verification verified
```

- Lexical FTS5 is the default: space-separated terms must all match. Start from
  a distinctive project or component token, not a full sentence; widen only
  after seeing what the first pass returned.
- `--mode vector` or `hybrid` requires an explicitly built local ONNX index
  (`--model-dir`, see the README). Never silently substitute lexical hashes or
  a hosted embedding API.
- `--state superseded` inspects replaced records; `--verification unverified`
  isolates unproven ones. Project and importance filters apply before limits.
- A hit is a snippet, not the decision: open `findings.py show <id>` or the
  source file before relying on it.
- Lifecycle badges: `[superseded by #N]` — resolve to the replacement before
  use; `[unverified]` — treat as unconfirmed.
- Empty result: try a materially better token or a supported `OR`, then report
  what was searched. No hits in scope does not prove that no policy exists.
- Composition: to keep portable patterns available while scoping to a project,
  query `--project <slug>` and `--project portable`, or query globally.

`memory/scripts/memory-warmup.py` (diagnostic; `--full` for the complete feed)
ranks high/normal unanchored items above checkpoints and shows each active
invariant's verification status.

## Handoff records

Keep a handoff compact: the command run, the state/scope/environment, the
result, and what invalidates it (a change, a failure, an unresolved concern).
Reuse it while that state is unchanged instead of building a tracking
subsystem around it.

Tag vocabulary: `architecture`, `engineering`, `security`, `performance`,
`devops`, `testing`, `frontend`, `backend`, `database`, `api`.