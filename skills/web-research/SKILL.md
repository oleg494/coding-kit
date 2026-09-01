---
name: web-research
description: 'Use when you need a fact from the outside world: "find out", "look up", "what do they say about", "how it works", "compare", "find information". Protocol: web search → primary sources → cross-check → answer with sources. Do not use for searching the knowledge base (business-wiki) or for facts already in the Wiki.'
metadata:
  version: "3.7.0"
---

# Web Research — facts from the outside world

## Workflow

1. **Formulate your search query.** What exactly do you need to find out? 2-3 wordings.
2. **Web search.** Use the available tools (web_search, curl, browser).
3. **Primary sources, not retellings.** Official docs > articles > forums. Don't trust retellings without a link to the original.
4. **Cross-check.** Minimum 2 independent sources for each key fact. 1 source = not an answer.
5. **Dating.** When is the data current? "As of August 2026..."
6. **Answer with sources.** Every fact with a link. Mark unverified claims "verify".

## Source hierarchy & fallback (403/429/captcha)

1. **Official docs / GitHub repo / source code** — the primary source.
2. **Issue trackers, ADRs, engineering blogs** — industry practice.
3. **Direct HTTP fetch of the page** (`read` on the URL) — when search engines
   block you.

On 403/429/captcha: switch to the next level immediately; never stop the task
and never fill the gap by inventing a result. If every level fails: "not
verified — sources unreachable", and name exactly what was tried.

## Research depth

- **Quick fact** (date, number, definition) — 2-3 sources, one pass.
- **Medium research** (comparison, "how it works") — 5-7 sources, primary sources + expert articles.
- **Deep research** (strategy, technology choice, "what do they say about") — 10+ sources, breadth → depth: canonical repos, PRs, issues, ADRs, official guides.

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
- **Offer to save.** "Save this in the Wiki?"

## Gotchas

- The first link in search results isn't always the primary source. Check who the author is and where the data comes from.
- SEO articles (Medium, Dev.to) often retell documentation with errors. Go to the original.
- Publication date: a 2023 article about a technology may be outdated.
- Don't use web search for facts already in the Wiki — first `db-tools/search.py`.