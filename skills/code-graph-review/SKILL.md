---
name: code-graph-review
description: 'Use when a multi-file change, a rename, or an explicit graph review needs impact analysis — what it breaks, which execution paths it touches, which symbols go dead. Optional helper: works when the code-review-graph MCP and a built graph exist, otherwise native LSP/source search answers direct impact. Not for locating code (use find/grep) and not for judging whether the change is good (use code-review-and-quality).'
license: MIT
compatibility: 'git repo; code-review-graph MCP when available, otherwise LSP/source search'
metadata:
  version: "6.0.0"
---

# Code graph review: what will the change break

Answers "what does this N-file change break", alongside a quality review rather
than instead of one: it produces the impacted paths and symbols that a reviewer
judges, and issues no verdict of its own. Applies when a change spans several
files, to a rename, to a blast-radius or affected-flow question, or to an
explicit graph review; a single-file edit with local callers needs only its
callers read.

The graph path applies only when the code-review-graph MCP server and a built
graph exist in this environment; otherwise use the native fallback. Nothing
obliges you to install or build a graph for a review. Never claim graph-level
findings (hubs, communities, flows) that a native search did not produce.

## Workflow (graph path — MCP present)

1. **Applicable diagnostics** — configured LSP and repository checks; unrelated
   ones are not a blocker.
2. **Graph freshness** — update incrementally only when writes are authorized;
   on a read-only review over a stale graph, use source/LSP and state the
   limitation.
3. **`detect_changes`** — diff → risk score, priorities (what to inspect first),
   test gaps. The main review tool.
4. **`get_impact_radius`** (BFS depth over the diff) and **`get_review_context`**
   (code snippets) — the blast radius itself.
5. **`get_affected_flows` / `list_flows`** — which user paths pass through the
   changed files.
6. **Structural questions only** — `get_hub_nodes`, `get_bridge_nodes`,
   `get_surprising_connections`, `get_architecture_overview`,
   `get_knowledge_gaps`, `get_suggested_questions`.
7. **Dead code and rename are analysis** — `refactor_tool(mode="dead_code")` and
   `refactor_tool(mode="rename")` return candidates and a per-site preview.
   `apply_refactor_tool` writes to the codebase, so it is not part of review;
   applying a plan needs an implementation task with authority to edit.
8. **Confirm dead-code candidates via LSP** (`find_references`) before reporting
   them removable: detection false-positives on callbacks and
   `Thread(target=...)` registrations.

## Native fallback (no MCP, or no graph)

- Turn the diff into changed symbol names, then enumerate direct callers with
  LSP `find_references` / `find_definition` or source search.
- Walk callers one level for shared code; report which call sites you checked
  instead of implying exhaustive reachability.
- Rename: search every usage of the old name and show the per-site preview.
- Dead code: "no references found in the sources searched", not "dead".

## Pitfall

The native path answers direct impact. Don't present it as graph-equivalent
whole-system analysis.