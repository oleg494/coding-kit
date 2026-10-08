---
name: code-graph-review
description: 'Understand "what this N-file change will break": blast radius over the diff, affected execution paths, dead code, rename impact. Use when the code-review-graph MCP is available and a graph exists, or when the user explicitly invokes a graph-based review; otherwise native source search/LSP (find references, definitions) covers change impact. Do not use for code search/navigation.'
license: MIT
compatibility: 'git repo; code-review-graph MCP when available, otherwise LSP/source search'
metadata:
  version: "4.8.0"
---

# Code graph review: what will the change break

Answers "what will this N-file change break". The graph path applies only when the code-review-graph MCP server and a built graph exist in this environment; otherwise use the native fallback — there is no obligation to install or build a graph for review. Never claim graph-level findings (hubs, communities, flows) that a native search did not produce.

## Workflow (graph path — code-review-graph MCP present)

1. **Choose applicable diagnostics** — use configured LSP and repository checks; unrelated diagnostics are not an automatic blocker.
2. **Check graph freshness** — update incrementally only when writes are authorized. For a read-only review with stale graph data, use current source/LSP and state the graph limitation.
3. **Run `detect_changes`** — diff → risk score, priorities (what to look at first), test gaps. This is the main review tool.
4. **Assess blast radius** — `get_impact_radius` (BFS depth over the diff), `get_review_context` (code snippets). Ask: "what will the N-file change break".
5. **Check affected flows** — `get_affected_flows`/`list_flows`: which user paths pass through the changed files.
6. **Architecture (if needed)** — `get_hub_nodes` (who is a hub), `get_bridge_nodes` (bridges), `get_surprising_connections`, `get_architecture_overview`, `get_knowledge_gaps`.
7. **Dead code / rename** — `refactor_tool(mode="dead_code")`; `refactor_tool(mode="rename")` → `apply_refactor_tool`.
8. **Verify dead-code false positives via lsp** (`find_references`), don't delete blindly.

## Native fallback (no MCP / no graph)

- List the changed symbols (diff → names), then find references/definitions via LSP or source search to enumerate direct callers.
- Walk callers one level for shared code; report which call sites you actually checked rather than implying exhaustive reachability.
- Rename impact: search all usages of the old name; show the replacement preview per site.
- Dead code: search for references; report "no references found in sources searched", not "dead" as an absolute.

## Table: task → tool (graph path)

| Task | Tool |
|---|---|
| change review (diff → risk → priorities) | `detect_changes` |
| blast radius of an N-file change | `get_impact_radius`, `get_review_context` |
| affected execution paths | `get_affected_flows`, `list_flows` |
| dead code | `refactor_tool(mode="dead_code")` |
| hubs/bridges/unexpected coupling | `get_hub_nodes`, `get_bridge_nodes`, `get_surprising_connections` |
| weak spots | `get_knowledge_gaps`, `get_suggested_questions` |
| rename with preview | `refactor_tool(mode="rename")` → `apply_refactor_tool` |

## Pitfalls

- **dead-code produces false positives** on callback patterns and `Thread(target=...)` — verify via lsp, don't delete blindly.
- A stale graph is not evidence of current reachability. Update only within authorization or use current source instead.
- The native path answers direct-impact questions; do not present it as graph-equivalent whole-system analysis.