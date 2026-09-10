---
name: architecture-simplicity
description: 'Use when the user wants to: design/redesign modules and layers, choose between a library and your own code, understand why a project became a god file, add an abstraction "just in case", evolve a DB schema without data loss, or review architecture. Covers: YAGNI until second need, stdlib-first, modules by change reason, shared core + thin adapters, config outside repo + defaults in code, schema evolution without DROP, provider fallback chain, unrepresentable invalid states, deleting dead code. Do not use for money (money-path-safety).'
license: MIT
compatibility: any language and stack, architecture design/review phase
metadata:
  version: "4.5.1"
---

# Architecture & simplicity: design principles

## 1. Simplicity and dependency

1. **YAGNI UNTIL SECOND NEED** — an abstraction without present value or clear change isolation is debt, not architecture. Unless separating pure logic from I/O or isolating a concrete boundary of change, inline until a second consumer appears. A layer you can remove means the same behavior with less code.
2. **STD LIB / PLATFORM BEFORE DEPENDENCY** — a new dependency costs more than 30 lines of your own code (often). Start with stdlib/native; add a dep only if the pain is measurable. moment.js for a single format = no.
3. **SEPARATE MODULES BY CHANGE REASON** — generators.py, payments.py, access.py, bot.py — different axes of change. A PDF feature must not touch billing. No 3000-line god file.
4. **SHARED CORE, THIN ADAPTERS** — one business logic; Telegram/CLI/desktop is a shell (I/O + auth + UX). A polish bug is fixed in one place, both clients stay fine.
5. **STOP WHEN THE NEXT ABSTRACTION DOESN'T PAY RENT THIS WEEK** — an abstraction must pay for itself now, not "someday".

Simplicity must preserve the complete requested behavior. A smaller feature
set is not a simpler implementation of the same requirement.

## 2. Config and evolution

- **CONFIG OUTSIDE REPO, DEFAULTS IN CODE** — secrets and ops tuning never in git; safe defaults in code; override via env.
- **SCHEMA EVOLUTION MUST NOT WIPE PROD** — deploy must not require DROP TABLE: CREATE IF NOT EXISTS + ALTER ADD COLUMN ignore-if-exists.
- **FLAGS FOR REAL ROLLOUT NEEDS** — use config for operational variation, not to avoid a required cutover or add hypothetical compatibility paths.
- **DETERMINISTIC REBUILD > STALE CACHE** — rebuilding deterministically beats living with a stale cache.

## 3. Code patterns

- **EXPLICIT SPEND ORDER IN ONE FUNCTION** — the debiting order (free→bonus→paid) is one algorithm in one place.
- **PROVIDER FAILURE POLICY** — implement fallback only when the availability contract requires it and an authorized compatible provider exists; otherwise fail clearly. A second vendor is not a default feature.
- **PURE FUNCTIONS FOR ASSEMBLE/EXPORT; IMPURE AT THE EDGES** — assembly/export are pure functions; I/O at the boundaries.
- **MAKE ILLEGAL STATES UNREPRESENTABLE** — separate fields over boolean soup: `status: active|finished` instead of flags.
- **COMMENTS EXPLAIN WHY AND CEILING** — not what the line does, but why and what ceiling.
- **DELETE DEAD CODE; DON'T COMMENT IT OUT FOREVER** — dead code gets removed.
- **NAMING: VERBS THAT MEAN $** — charge_seconds, apply_referral, can_afford — verbs with money semantics.
- **FLOAT MONEY IS EVIL LONG-TERM** — money is not float; minutes are fine if consistent + tested.

## Workflow (order of application)

1. **Define module boundaries by change reason.** Different axes → different modules. No 3000-line god file.
2. **Check every abstraction against YAGNI.** Keep genuine change-isolation boundaries; remove layers without present value, not every single-consumer unit.
3. **Check dependencies.** stdlib/platform first; a dep only if the pain is measurable.
4. **Separate core and adapters.** One business logic; thin shells.
5. **Check config and secrets.** Secrets out of git; defaults in code; override via env.
6. **Check schema evolution.** Deploy without DROP TABLE.
7. **Check key patterns.** Debiting order in one function. Fallback chain. Invalid states unrepresentable.
8. **Remove dead weight.** Dead code gets deleted. Comments WHY, not WHAT.

## Architecture review checklist

- [ ] abstractions have present value or a genuine change-isolation boundary
- [ ] dependency justified (stdlib first)
- [ ] modules separated by change reason
- [ ] one business core; thin adapters
- [ ] secrets outside the repo; defaults in code
- [ ] schema evolves without DROP
- [ ] debiting order in one function
- [ ] provider failure behavior meets actual availability requirements
- [ ] invalid states unrepresentable
- [ ] dead code removed; WHY comments