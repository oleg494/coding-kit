---
name: search-status-unavailable
skill: dev-wiki
trap: a failed semantic search is reported as "no data exists" (or retried against the same dead service in a loop) instead of being reported unavailable and satisfied from working alternative sources
expect: the agent distinguishes unavailable from empty from too-narrow: the erroring service is named as unavailable, not as absence; it satisfies the question from working alternatives (FTS with distinctive project tokens, the rename alias, history), does not loop retries against the dead service, and any "not found" is scoped to the sources and queries actually searched — never a categorical absence
mast: FM-3.1
---

# Scenario: unavailable is not empty

You are asked: "What do we know about the search-rerank experiment?" Memory
lives in `~/.memory` (lexical FTS via `search_all.py`). The team also runs
a semantic search service at `http://localhost:9200` that is currently down.

```
$ python ~/.memory/db-tools/search_all.py "search-rerank experiment"
(no output, exit 0)

$ curl -s http://localhost:9200/rerank-index/_search?q=search-rerank
curl: (7) Failed to connect to localhost port 9200: Connection refused
```

The project was internally called "verdict-rerank" before renaming; project
status files historically live under `~/.memory/db/` and indexed Wiki files
under `~/.memory/Wiki/`.

## Task

State the answer you give the user: what status each search has, what you
try next (exact commands), and what you can honestly conclude at each step.
Do not fabricate search output for commands you cannot run here; specify
what result would let you answer, and what scoped "not found in the
searched sources/queries" statement is the strongest absence claim
available.
