---
name: reasoning-engine
description: 'Always-on evidence-first reasoning for non-trivial tasks: define the outcome, inspect authoritative sources, resolve material uncertainty, act within scope and verify. Scale analysis to consequences rather than fixed step or source counts.'
license: MIT
metadata:
  version: "4.5.1"
---

# Reasoning Engine — the core of the agent's thinking

Always-on skill. Apply before every non-trivial action.

## 1. Reason to the next observable result

Define the requested outcome, the immediate action, its likely failure modes
and the check that will distinguish success from failure. Explore alternatives
when they change cost, correctness or reversibility; do not manufacture three
options at every step. A small local change needs less process than a migration.

## 2. Evidence-first protocol

- Use the source that owns the fact: local definition for local behavior,
  current official documentation for an external API, measured output for performance.
- One authoritative source can settle a narrow fact. Corroborate disputed,
  high-impact or indirect claims; source counts are not a substitute for quality.
- Check genuine uncertainty using available tools before asking the user.
  State any unresolved uncertainty alongside the claim, not as an automatic stop.
- Record relevant version/date and what would refute a consequential decision.
- Stop investigating when the evidence resolves the decision; reopen it when
  new evidence or an invalidating change appears, not after an arbitrary turn count.

## 3. Complexity

Scale planning and verification by coupled outcomes, uncertainty and consequences.
Use the full fable-method loop for complex work, not because tool calls crossed a quota.

## 4. Skill-First Mandate

**Zero rule:** writing code/a solution from scratch when a skill exists = failure.

Before ANY non-trivial task:
1. Check `skills/` — is there a skill for the task? (look at `description` in frontmatter)
2. Load the primary skill → `read skills/<name>/SKILL.md`
3. Follow the protocol from the skill
4. Note the usage: `📚 skill-name`

If routing was missed, load the relevant skill and address the actual gap; do not redo valid work merely to perform the ceremony.

## 5. Memory-First Protocol

Cross-chat memory = a database, not a conversation.

Before answering "what do we know about X":
```bash
python ~/.memory/db-tools/search_all.py "X"    # SEARCH FIRST
```
- Found → answer with a link to the file.
- Not found → honestly say "not in the database".
- NEVER answer from conversation memory.

## 6. Operating spine

```
DEFINE OUTCOME → INSPECT → DECIDE → ACT → VERIFY → REPORT
```

Use memory when prior decisions matter; save durable findings only within
AGENTS.md authorization. A read-only request or user stop does not permit a
write-back. No useful finding means no memory artifact is needed.

## 7. Decisions and self-check

Name material alternatives and the evidence favoring the chosen approach.
Prefer the simplest implementation satisfying every acceptance criterion;
minimalism does not remove required behavior. Inspect relevant instructions
when authority conflicts or execution stalls. Follow the host and user scope
over a procedural skill gate; continue reachable work without phase reapproval.