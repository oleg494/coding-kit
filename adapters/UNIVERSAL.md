# Universal Adapter — coding-kit

> Developer kit: superpowers, YAGNI, TDD, cross-chat memory. For any agent that reads AGENTS.md and skills.

## Install (general principle)

Terminology: agents have a "skills dir" (progressive disclosure) and a "rules dir" (always loaded, e.g. ~/.claude/CLAUDE.md, AGENTS.md).

1. Rules: merge a pointer to the clone's absolute `OPS.md` path into the host rules; load it once. Preserve unrelated rules. `AGENTS.md` is only the repository router.
2. Skills: copy/link the 37 skills declared in `profile.yml`, not every directory under `skills/`. Bodies load on explicit invocation or an unresolved domain question.
3. Memory (external): `~/.memory/` — Wiki + db-tools engine + research.db. Kit and memory are separate: the kit is pure methodology, knowledge lives in the memory root.

## Rule fragments and native harness mechanisms

OPS.md owns the core contract. Topic-specific procedures load only when they
resolve missing domain detail; a matching broad label is not a cascade.
Memory retrieval is demand-driven, not an unconditional startup feed.
Map integration to the host's actual native mechanism:

| Harness | Native mechanism | Kit mapping |
|---------|------------------|-------------|
| Claude Code | `.claude/rules/*.md` with `paths:` frontmatter | skill-triggered (kit form); or point a rule file at the skill's SKILL.md section |
| Codex CLI | per-directory AGENTS.md concatenation, closest wins | skill-triggered (kit form); drop a project AGENTS.md stub referencing the skill |
| Hermes | `skills.external_dirs` + kit projection via `hermes_adapter.py` | [hermes.md](hermes.md) — verified contract |

Receiving skills today: money rules -> `money-path-safety`; testing/TDD gate ->
`testing-discipline`; destructive-command list -> `git-workflow-and-versioning`;
memory-trust/ASI06 -> `security-and-hardening`. OPS.md keeps one-line pointers.

## Specific agents

### Claude Code / OMP

Claude Code: rules in `~/.claude/CLAUDE.md`, skills in `~/.claude/skills/`.
OMP: rules in `~/.omp/agent/AGENTS.md`, skills in `~/.agents/skills/` with
user-agent skill discovery enabled. Keep platform-specific configuration
outside the kit contract; inspect active discovery settings rather than
assuming the two hosts share a skill directory.


<!-- Historical Gemini CLI chat-JSON archives remain readable via
     eval/transcript_normalize.py --source gemini. -->

### Hermes
```bash
# Supported path: scripts/tools/hermes_adapter.py (external-root projection,
# curated ownership, delimited SOUL block). See adapters/hermes.md for the
# verified contract — do NOT rsync skills into ~/.hermes/skills/ anymore.
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

File presence/consistency (what `scripts/doctor.py` skills-sync checks) is
NOT activation. Verify integration by behavior: ask the agent to show its
method (plan → TDD → implement → verify → report) and to search memory for
a topic: it must route through
`python ~/.memory/db-tools/search_all.py "X"` (or `findings.py search`),
not answer from conversation. Behavior over identity. No kit check proves
model activation without launching your harness; the kit claims none.