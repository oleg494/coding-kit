---
name: web-research
description: 'Use when you need a fact from the outside world: "find out", "look up", "what do they say about", "how it works", "compare", "find information". Protocol: web search → primary sources → cross-check → answer with sources. Do not use for searching the knowledge base (business-wiki) or for facts already in the Wiki.'
license: MIT
metadata:
  version: "4.5.1"
---

# Web Research — facts from the outside world

## Workflow

1. **Define the missing external fact.** Local code and established project facts do not need web corroboration.
2. **Read known primary URLs directly; search when the source is unknown.** Use a browser only for interactive or dynamically rendered content.
3. **Primary sources, not retellings.** Official docs, original research or source code; check the actual version and applicability.
4. **Cross-check where material.** One authoritative source can establish a narrow fact; seek independent evidence for disputed, indirect or high-impact claims.
5. **Dating.** Include the relevant version/date for time-sensitive facts.
6. **Answer with sources.** Link external claims and identify remaining uncertainty. Do not invent facts when a source is unavailable.

## Source hierarchy & fallback (403/429/captcha)

1. **Official docs / GitHub repo / source code** — the primary source.
2. **Issue trackers, ADRs, engineering blogs** — industry practice.
3. **Direct HTTP fetch of the page** (`read` on the URL) — when search engines
   block you.

On 403/429/captcha, try another legitimate source or access method without
bypassing access controls. If sources remain unreachable, name the unresolved
fact and what was tried; finish the parts that available evidence supports.

## Research depth

Use enough evidence to resolve the question, not a fixed number of queries or
pages. A definition can need one source; a technology comparison may require
multiple alternatives, benchmarks and counterexamples. Stop when further
search cannot materially change the answer.

## What to look for

| Type of information | Where to look |
|---------------|-----------|
| API / library | Official documentation, GitHub README, source code |
| Industry practice | GitHub issues, ADRs, engineering blogs, Thoughtworks Tech Radar |
| Bug / error | GitHub issues, Stack Overflow, official bug tracker |
| Tool comparison | Benchmarks, practitioner articles, Hacker News discussions |
| Regulations / laws | Official sources (.gov, legal databases) |

## Answer

- **Result first line.** What was found, briefly.
- **Details with sources.** Every fact with a link.
- **Caveats.** What wasn't verified, what's in question.
- **Memory.** Save only durable findings within existing authorization; do not add a save-confirmation ritual to every answer.

## Gotchas

- The first link in search results isn't always the primary source. Check who the author is and where the data comes from.
- SEO articles (Medium, Dev.to) often retell documentation with errors. Go to the original.
- Publication date: a 2023 article about a technology may be outdated.
- Don't use web search for facts already in the Wiki — first `db-tools/search.py`.