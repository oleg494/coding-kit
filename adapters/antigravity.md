# Antigravity IDE + Gemini — Setup Guide (coding-kit)

> How to wire the coding-kit into Antigravity IDE and Gemini hosts.

## 1. What Antigravity / Gemini reads

- Antigravity user-level global rules (`<RULE[user_global]>`): `~/.gemini/GEMINI.md` (and `~/AGENTS.md` for repo/generic hosts).
- Skills: `~/.gemini/skills/` and `~/.agents/skills/` — SKILL.md dirs (or junctions to `skills/`).
- Workspace: open your project folder; per-project `AGENTS.md` overrides workspace context.

## 2. Install

### Automated rollout (recommended)
```bash
python scripts/install.py        # bootstrap ~/.memory, engine junction, wiki index
python scripts/tools/deploy.py   # sync owned skills + refresh user routers (~/.gemini/GEMINI.md, ~/AGENTS.md, ...)
```

### Step 1: Rules
Merge a pointer to the clone's absolute `OPS.md` path into `~/.gemini/GEMINI.md` and `~/AGENTS.md`.
Preserve existing instructions and `CODEGRAPH` blocks. Load the contract once; do not copy the
repository router with a relative link into an unrelated directory.

### Step 2: Skills
Copy or link only the owned skills declared in `profile.yml` into
`~/.gemini/skills/` and `~/.agents/skills/`, preserving unrelated skills. A full-directory wildcard
would also copy third-party sources and is not the kit ownership contract.

### Step 3: Memory
Memory lives outside the kit: `~/.memory/` (Wiki + db-tools + research.db). Rebuild indexes:
```bash
python ~/.memory/db-tools/build.py
python ~/.memory/db-tools/build.py -r <project-root> -o ~/.memory/db/<name>.db
```

### Step 4: Verify
In the IDE ask the agent how it will handle a small bug fix (it should name acceptance, the check it will run and the report, per OPS.md) and to search memory for X: it must run `python ~/.memory/db-tools/search_all.py "X"`, not answer from the conversation.

## 3. What the agent does after install

```
STARTUP   read the canonical OPS.md once; no automatic memory feed
QUESTION  known → search_all.py "X" → answer with the source
TASK      OPS.md: acceptance → change → check → report; one skill per open question
"write"   hierarchy: portable → ~/.memory/Wiki/; project → WORK/<proj>/docs/
```