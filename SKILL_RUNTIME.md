# Coding Agent OS — Skill Runtime

> **v3.4.5** | For platforms with ≥16K context.
> Superpowers: plan → TDD → implement → verify → report.
> 8–16K context → core mode: OPS.md §1-5 + skill routing table only.
> <8K context → compact mode: irreducible core retains action authorization rules, stop conditions, calibrated uncertainty, and applicability exceptions (see §1 below).
> Answer the user in THEIR language. Everything else — English.
## For every non-trivial task

### 1. SUPER POWERS (always)

```
PLAN → TDD → IMPLEMENT → VERIFY → REPORT
```

### 2. PLAN
- Define "what done means" — concretely, observably.
- Name the scope: files you touch, files you do NOT touch.
- Complex task (>3 files) → split into atomic tasks.

### 3. TDD
- Red test → green code → refactor.
- No code without a failing test.
- Bug fix → Prove-It Pattern: a test reproducing the bug FIRST.

### 4. IMPLEMENT
- The minimal change that makes the test green.
- YAGNI: nothing beyond the test.
- Match surrounding style.

### 5. VERIFY
- Test green? → observed.
- Tests appropriate to the change green? → ran them; broaden when scope
  warrants (shared code touched, or a failure the targeted check exposed).
- Build intact? → checked.
- Bug fix → TWINS: searched for the same pattern in the codebase.

### 6. REPORT
- Result first line.
- Files touched.
- What was verified.

## Skill loading

```
1. IDENTIFY: check skills/ — is there a skill for the task?
2. LOAD: read skills/<name>/SKILL.md
3. APPLY: follow the Protocol/Workflow section
4. MARK: 📚 skill-name
```

## Cross-chat memory (hierarchy)

```bash
python ~/.memory/scripts/memory-warmup.py                    # warmup
python ~/.memory/db-tools/search_all.py "X"                  # search all bases
python ~/.memory/db-tools/build.py                           # rebuild index
python ~/.memory/db-tools/findings.py add "topic" --text "conclusion" --source path
```

Boundary rule: portable → `~/.memory/Wiki/`; project-specific → `WORK/<project>/docs/` + `build.py -r`.

## Irreducible Core & Exceptions

- **Authorization rules:** User instructions outrank kit skills. Commits happen only if requested by user or repo convention. Destructive commands require user confirmation. Reversible local changes proceed without approval stall.
- **Uncertainty & stop conditions:** Label low-confidence facts honestly; don't guess. Stop when blocked by environment, permissions, or 3 failed cycles.
- **Applicability exceptions (When NOT to use full cycle):**
  - One-line fix, typo → verify is enough.
  - Pure documentation → plan + verify.
  - Read-only investigation/review → findings and recommendation only; no side-effect memory or file writes unless asked.

## Never
- Write code without a plan and a test
- Build abstractions without present value / clear change boundary
- Add dependencies without measuring the pain
- Claim "done" without evidence
- Answer from conversation memory — use the database