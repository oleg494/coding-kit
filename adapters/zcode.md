# ZCode (Z.ai) — Setup Guide (coding-kit)

> How to wire coding-kit into ZCode (Z.ai Agentic Development Environment & CLI).

## 1. What ZCode reads

- Global instructions: `~/.zcode/AGENTS.md` (and `~/.zcode/CLAUDE.md` for compatibility).
- Global skills: `~/.zcode/skills/` — directories with Hermes-compatible `SKILL.md`.
- Workspace instructions: `<project-root>/AGENTS.md`.
- Workspace skills: `<project-root>/.zcode/skills/`.

## 2. Install

### Step 1: Rules
Merge a pointer to the clone's absolute `OPS.md` path into
`~/.zcode/AGENTS.md`, preserving existing rules. Load it once. Copying the
repository router alone leaves its relative contract link unresolved.

### Step 2: Skills
Copy or link only skills declared in `profile.yml` into `~/.zcode/skills/`,
preserving unrelated skills. Linking the entire `skills/` directory also
exposes any user-owned third-party directories placed beside kit skills;
use that layout only if this broader discovery is intended.

### Step 3: Memory
Memory lives outside the kit: `~/.memory/` (Wiki + db-tools + research.db).
Rebuild indexes:
```bash
python ~/.memory/db-tools/build.py
```

### Step 4: Verify
In ZCode chat or CLI:
- Ask the agent to describe how it will handle a small bug fix: it should
  name acceptance, the check it will run and the report, per OPS.md.
- Ask it to search memory for X: it must run a database search
  (`search_all.py`), not answer from the conversation.
