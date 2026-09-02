---
name: code-graph-review
description: 'Use BEFORE a commit or change review, when you need to understand "what this N-file change will break": blast radius over the diff, affected execution paths, dead code, architectural hubs/bridges, weak spots, rename with preview. Do not use for code search — CRG is for structural diff analysis, not navigation.'
compatibility: git repo with a built graph (code-review-graph MCP)
metadata:
  version: "4.1.0"
---

# Code graph review: what will the change break

The code-review-graph MCP server answers "what will this N-file change break" — impact/blast radius over the DIFF, dead-code, communities, flows.

## Workflow (order of application)

1. **Changes ready → diagnose first** (lsp): 0 errors before any linter.
2. **Rebuild the graph** — `build_or_update_graph_tool` (incrementally). A stale graph = false analysis.
3. **Run `detect_changes`** — diff → risk score, priorities (what to look at first), test gaps. This is the main review tool.
4. **Assess blast radius** — `get_impact_radius` (BFS depth over the diff), `get_review_context` (code snippets). Ask: "what will the N-file change break".
5. **Check affected flows** — `get_affected_flows`/`list_flows`: which user paths pass through the changed files.
6. **Architecture (if needed)** — `get_hub_nodes` (who is a hub), `get_bridge_nodes` (bridges), `get_surprising_connections`, `get_architecture_overview`, `get_knowledge_gaps`.
7. **Dead code / rename** — `refactor_tool(mode="dead_code")`; `refactor_tool(mode="rename")` → `apply_refactor_tool`.
8. **Verify dead-code false positives via lsp** (`find_references`), don't delete blindly.

## Table: task → tool

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
- The graph builds/updates incrementally: `build_or_update_graph_tool` after changes — otherwise the data is stale.