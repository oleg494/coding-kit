# Universal Adapter — coding-kit

> Developer kit: superpowers, YAGNI, TDD, cross-chat memory. For any agent that reads AGENTS.md and skills.

## Install (general principle)

Terminology: agents have a "skills dir" (progressive disclosure) and a "rules dir" (always loaded, e.g. ~/.claude/CLAUDE.md, AGENTS.md).

1. Rules: point the agent's rules file at `AGENTS.md` (or copy its content). Memory paths use the `~/.memory` convention — env `MEMORY_ROOT` overrides.
2. Skills: copy/link `skills/` into the agent's skills dir. Hermes-format SKILL.md, 42 skills.
3. Memory (external): `~/.memory/` — Wiki + db-tools engine + research.db. Kit and memory are separate: the kit is pure methodology, knowledge lives in the memory root.

## Rule fragments -> harness mechanisms (v3.8.0)

The kit keeps OPS.md a thin always-loaded core; topic rules live as "fragments"
in their JIT home skills and load only when the skill's description fires — the
portable equivalent of path-scoped rules. Map to your harness natively when it
has the mechanism:

| Harness | Native mechanism | Kit mapping |
|---------|------------------|-------------|
| Claude Code | `.claude/rules/*.md` with `paths:` frontmatter | skill-triggered (kit form); or point a rule file at the skill's SKILL.md section |
| Codex CLI | per-directory AGENTS.md concatenation, closest wins | skill-triggered (kit form); drop a project AGENTS.md stub referencing the skill |
| Antigravity | user-level `~/AGENTS.md`, `~/.agents/skills/` | skill-triggered (kit form) — no extra work |
| Hermes | `skills.external_dirs` config | skill-triggered (kit form) — no extra work |

Receiving skills today: money rules -> `money-path-safety`; testing/TDD gate ->
`testing-discipline`; destructive-command list -> `git-workflow-and-versioning`;
memory-trust/ASI06 -> `security-and-hardening`. OPS.md keeps one-line pointers.

## Specific agents

### Claude Code / OMP
```bash
# rules: ~/.claude/CLAUDE.md — append the router
# skills: ~/.claude/skills/ — copy or junction
cp -r skills/. ~/.claude/skills/   # contents; safe when the dir exists
```


<!-- Gemini CLI retired by Google 2026-06-18; Antigravity is the successor.
     Historical chat-JSON archives remain readable via
     eval/transcript_normalize.py --source gemini. -->

### Hermes
```yaml
# rules: SOUL.md gets the kit soul (AGENTS.md content)
# skills: config.yaml → skills.external_dirs:
#   - <kit>/skills
```

### Antigravity
```bash
# rules: ~/AGENTS.md (user-level)
# skills: ~/.agents/skills/
```

### ZCode (Z.ai)
```bash
# rules: ~/.zcode/AGENTS.md
# skills: ~/.zcode/skills/ (junction recommended)
```

## Verify

Ask the agent to show its method (plan → TDD → implement → verify → report) and to search memory for a topic: it must route through `python ~/.memory/db-tools/search_all.py "X"` (or `findings.py search`), not answer from conversation. Behavior over identity.