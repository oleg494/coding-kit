---
name: web-research
description: 'Use when a fact from outside the project is needed: "find out", "look up", "what do they say about", "how it works", "compare", "find information", "is this still true". Identify or read the primary source first — open a known URL directly, search only when the owner of the fact is unknown — then cross-check material claims, date them, and answer with links. Not for the local knowledge base or recorded project facts (use dev-wiki) or consequential tool/library decisions (use production-first-decisions).'
license: MIT
metadata:
  version: "6.0.0"
---

# Web Research — facts from the outside world

## Workflow

1. **Define the missing external fact.** Local code, project docs and recorded
   decisions do not need web corroboration; a fact already in the Wiki is
   retrieved from there.
2. **Identify or read the primary source.** If you know who owns the fact
   (vendor docs, a repo, a spec, a law), open that URL directly with the
   reader. Search only when the owner is unknown, then navigate from the
   result to the original. Use a browser only for interactive or
   dynamically rendered content.
3. **Prefer primary over retelling.** Official documentation, original
   research, source code, the standard text; check the actual version and
   whether the answer applies to it.
4. **Cross-check where material.** One authoritative source settles a narrow
   fact; disputed, indirect or high-impact claims need independent evidence.
5. **Date the claim.** State the version or date for anything time-sensitive;
   say what may have changed since.
6. **Answer with sources.** Link every external claim and name what stayed
   unverified. Never fill a gap with invented facts: an unavailable source is
   a reported limitation, not a licence to guess.

## When access fails (403/429/captcha/paywall)

Try another legitimate source or access path — the project's own mirror, the
repo, a cached or archived copy, a different official page — without bypassing
access controls, signing up, or paying automatically. If the fact stays
unreachable, name it, list what you tried, and finish the parts the available
evidence supports.

## Research depth

Use enough evidence to resolve the question, not a fixed count of queries or
pages. A definition can need one source; a comparison needs the alternatives,
their versions and any benchmark that speaks to the decision. Stop when more
search cannot change the answer.

## Where the fact usually lives

| Kind of fact | Owner to start from |
|---|---|
| API, library, CLI behavior | Official docs, README, changelog, source code |
| Industry practice, adoption | Engineering blogs, ADRs, issue threads, tech radars |
| Bug, error message | Project issue tracker, release notes, Q&A with an accepted answer |
| Tool or approach comparison | Reproducible benchmarks, practitioner reports with method |
| Regulation, standard, licence | The issuing body's own text (.gov, ISO/IEC, licence file) |

## Answer

- **Result first line.** What was found, in one sentence.
- **Details with links.** Each fact carries its source.
- **Caveats.** Unverified parts, version sensitivity, conflicting sources.
- **Memory.** Durable findings go through dev-wiki routing; a research run
  does not create its own memory policy.

## Gotchas

- The first search hit is often a retelling. Check who authored it and where
  the numbers come from.
- SEO farms and AI-generated posts reproduce docs with errors. Go to the
  original.
- Publication date is not the version date: a 2024 article may describe a
  behavior removed in 2026.
- An unanswered issue thread is evidence of a problem, not of its fix;
  read the resolution state.