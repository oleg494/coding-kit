# Antigravity IDE + Gemini — Setup Guide (coding-kit)

> How to wire the coding-kit into Antigravity IDE.

## 1. What Antigravity reads

- User-level instructions: `~/AGENTS.md` (home directory, applies to all workspaces).
- Skills: `~/.agents/skills/` — SKILL.md dirs.
- Workspace: `WORK/` is the typical opened folder; per-project AGENTS.md would go there.

## 2. Install

### Step 1: Rules
Merge a pointer to the clone's absolute `OPS.md` path into `~/AGENTS.md`.
Preserve existing instructions. Load the contract once; do not copy the
repository router with a relative link into an unrelated directory.

### Step 2: Skills
Copy or link only the 37 owned skills declared in `profile.yml` into
`~/.agents/skills/`, preserving unrelated skills. A full-directory wildcard
would also copy third-party sources and is not the kit ownership contract.

### Step 3: Memory
Memory lives outside the kit: `~/.memory/` (Wiki + db-tools + research.db). Rebuild indexes:
```bash
python ~/.memory/db-tools/build.py
python ~/.memory/db-tools/build.py -r <project-root> -o ~/.memory/db/<name>.db
```

### Step 4: Verify
In the IDE ask the agent to show its method (plan → TDD → implement → verify → report) and to search memory for X: it must route through `python ~/.memory/db-tools/search_all.py "X"`, not answer from conversation. Behavior over identity.

## 3. What the agent does after install

```
STARTUP   read the canonical OPS.md once; no automatic memory feed
QUESTION  known → search_all.py "X" → answer with file link
TASK      superpowers: plan → TDD → implement → verify → report
"write"   hierarchy: portable → ~/.memory/Wiki/; project → WORK/<proj>/docs/
```