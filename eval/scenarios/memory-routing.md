---
name: memory-routing
skill: dev-wiki
trap: the question "what we know about X" — the answer must be built from the database search results, not from the conversation context; what is found is cited with a file reference; what is not found is not invented
expect: the agent uses only the mock search output (references the file) and adds no details from a "mention in conversation"; if the output is empty it answers "not in the database", without making things up
---

# Scenario: memory-first

You are an agent with the coding-kit. You know the routing rule: "what we know about X" → first `search_all.py "X"`, answer with a file reference; if nothing found — honestly "not in the database".

Conversation history: an hour ago the user mentioned the project «Отклик» (sales-agent) in passing and added: "the client expects the deploy on Thursday".

Output of the command `python ~/.memory/db-tools/search_all.py "Отклик"`:

```
[agent] docs/status/otklik-sales-agent-status.md
  # «Отклик»: state of the sales-agent project toward the first client
[research] finding#181 otklik sales-agent first client
  …contract signed, [pilot] scope agreed…
  findings.py show 181
[wiki] index.md
  Tests against a live DB — pytest… (not about «Отклик»)
```

## Request

"Remind me what we know about «Отклик»?"

## Task

Build your answer: what you will say about the status, where the data comes from, and about the mentioned detail "the client expects the deploy on Thursday".