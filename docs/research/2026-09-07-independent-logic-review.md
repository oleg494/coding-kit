# Independent logic review — policy coherence, memory and evidence (2026-09-07)

**Date:** 2026-09-07  
**Reviewer:** Notion AI; independent maintainer-requested analysis  
**Status:** design review and proposed experiments; nothing implemented or benchmarked  
**Baseline:** local `VERSION` = `4.2.0`; GitHub parity and installed-host behavior not established  
**Companion:** [Independent code review](2026-09-07-independent-code-review.md)

## 1. Executive judgment

coding-kit has a defensible purpose: make an agent externalize working
knowledge, declare scope, inspect evidence, and stop presenting intention as
completion. Its strongest ingredients are memory, concrete domain gotchas,
and independently checkable outcomes. These should be preserved.

The weakest ingredient is the composition of the rules. Several files act as
controllers for the same decision: whether to ask, what process to use, what
counts as verified, and when to stop. The agent must reconcile those rules
while also solving the user's problem. More mandatory text can therefore
increase both apparent discipline and decision overhead without improving
the delivered outcome.

**Recommendation:** consolidate a small, coherent control contract around
existing mechanisms; do not add another mandatory meta-workflow. Treat a
lighter controller as a testable candidate, not a proven optimization.

## 2. Scope and evidence discipline

This is a logic review, not a second Python defect hunt. Instructions were
read as product material, not adopted as this reviewer's instructions.
Sources include AGENTS/OPS/runtime/profile, relevant method/memory/review
skills, adapters, memory interfaces, and the project's recorded experiments.
Two additional automated read-only review passes informed the analysis;
this is not external human validation or a field trial.

Evidence labels used below:
- **Observed:** a rule, interface or contradiction present in inspected text.
- **Reported:** an earlier result described in a repository artifact; not rerun.
- **Hypothesis:** a plausible behavioral consequence requiring a live test.
- **Proposal:** a design/experiment recommendation, not an implemented feature.

No kit scripts, tests, model benchmarks, deployments or private memory
operations ran. No personal session transcripts, external comparison sites,
or `.worktrees` were inspected in this pass. Only the two review documents
were added to the requested `docs/research/` destination.

## 3. What the system actually does

The practical architecture is a policy library plus memory/search tools,
interpreted by a host agent. It is not an OS-level sandbox or deterministic
workflow engine. The host supplies execution, permissions, context loading,
and much of the actual decision-making.

```text
host capabilities + user intent + allowed effects
  -> choose task shape and relevant procedure
  -> retrieve project evidence / past conclusions
  -> plan, act and verify within the chosen scope
  -> report the observed outcome and remaining uncertainty
  -> optionally retain useful knowledge for a future session
```

There are three feedback loops, with different failure modes:
1. **Execution:** plan -> tests -> action -> verification. It reduces careless
   work, but a mistaken acceptance criterion can produce a confidently wrong result.
2. **Memory:** conclusion -> storage -> retrieval -> new decision. It reduces
   rediscovery, but can repeatedly reinforce an old interpretation.
3. **Kit evolution:** incidents/evals -> new rules -> new evals. It enables
   learning, but can optimize compliance with kit-authored rules rather than
   usefulness on independent user tasks.

The objective should be successful authorized work with less rework and
unacceptable risk, at acceptable time and cost. Skill reads, checklist size,
report markers and test counts are diagnostics, not that objective.

## 4. Priority findings

### LR-01 — High: multiple controllers can authorize opposite transitions

**Observed:** `brainstorming`'s AUTHORIZATION-GATE allows authorized reversible
work. Its Three Paths/Spike still says "get a nod", while Checklist/Spike
says a read-only or throwaway probe needs no approval. Its architectural path
also prescribes committing the spec. `git-workflow-and-versioning` says each
successful increment gets a commit; `fable-method` Step 4.8 forbids commits
without explicit user instruction. `profile.yml` calls Fable always-on, while
Fable's description makes it a fallback when no task-specific skill applies.

**Scenario/hypothesis:** the same local investigation stalls or proceeds
according to which paragraph the model treats as decisive. A local feature
request with no git instruction can similarly acquire an unintended commit.
**Counterweight:** host > user > skills precedence and the new authorization
gate already exist. The old universal HARD-GATE has been removed. The gap is
peer-skill conflict when user intent does not enumerate every internal step.
**Proposal:** one source of truth for action authorization and workflow
selection; phase skills inherit it instead of restating their own gates.
[S1, S2, S4, S5, S6]

### LR-02 — Medium: the intent gate confuses an expected defect with unresolved requirements

**Observed:** Fable Step 4.1 defines X as current code, Y as the failing check,
Z as spec, then says not to edit if X, Y and Z do not all agree. In a normal
bug fix, X differs while Y and Z agree: that is the reason to change X.
Its compressed date-test example proceeds in exactly that kind of case.
**Scenario/hypothesis:** an agent reopens clarification after it has already
established both the defect and the intended behavior.
**Counterweight:** the authority order and examples let a capable model infer
the intended exception. This is a textual ambiguity, not a demonstrated deadlock.
**Proposal:** distinguish `code differs from agreed intent -> fix` from
`test and authoritative intent disagree -> resolve intent`. Agreement among
all three is a possible completion condition, not a repair precondition.
[S5: Step 4.1 and Compressed examples]

### LR-03 — High: review verdicts mix truth, completeness and merge policy

**Observed:** Fable Judge defines VERIFIED as every load-bearing claim
reproduced, but its count rule yields VERIFIED with up to two warnings.
The quality skill defines a warning as "must fix before proceeding; alone
not merge-blocking". UNVERIFIABLE exists in prose but is not an input to the
count-based verdict. A whole-work/directory audit also inherits a rule not
to report issues outside a diff.
**Scenario/hypothesis:** an unverified material claim gets a clean-sounding
label, or an unchanged but relevant defect disappears from a full audit.
**Counterweight:** the judge explicitly rejects invented success, inspects
weakened checks and says not to inflate caveats. These are valuable controls.
**Proposal:** separate claim state (observed pass/fail/unverified/skipped),
coverage and the decision to merge. Define diff-review and whole-system audit
as separate scopes. Warning counts can summarize; they cannot establish truth.
[S7, S8]

### LR-04 — Medium: evidence freshness is tied to a message instead of a checked state

**Observed:** verification-before-completion says the command must have run
"in this message". The same skill and Superpowers reject rerunning unchanged
checks without new changes, failures or unresolved concerns.
**Scenario/hypothesis:** a follow-up asking whether a test passed triggers
another expensive run despite no change to code or environment.
**Counterweight:** dated wording such as "the previous run passed" is honest;
the updated scope rule already discourages ceremony and whole-suite repetition.
**Proposal:** identify evidence by checked revision/snapshot, command,
environment, scope and time. Reuse it until an explicit invalidation condition
changes; report that provenance instead of treating the chat turn as a clock.
[S9: Iron Law, Gate Function; S10: Phase 4]

### LR-05 — High: the default memory route loses part of the trust lifecycle

**Observed:** findings has `supersedes`, verification fields and source
metadata; warmup deliberately surfaces contradictions and unanchored notes.
But AGENTS/OPS route recall through `search_all.py`. That interface returns
finding snippets/IDs without the superseded badge and verification metadata
provided by `findings.py search --json`. A drill-down hint exists, but the
main "found -> answer" route does not require resolving validity first.
**Scenario/hypothesis:** a lexical match to an older decision is reused as
current project truth, although the store already knows it was superseded.
**Counterweight:** this is NOT a memory system with no provenance or lifecycle.
The building blocks are unusually thoughtful; the default read path is weaker.
**Proposal:** retrieve candidates -> inspect source, scope and lifecycle ->
resolve conflicts -> answer. A hit is not authority. Current explicit user
constraints and current project evidence outrank an old stored conclusion.
[S1: routing; S2: memory; S11; S12; S13; S14]

### LR-06 — High: verification and remembering remain actions with side effects

**Observed:** dev-wiki has an optional save reflex and a project/global
boundary. AGENTS Session End separately lists warmup, log and rebuild steps.
The judge says to rerun every claimed verification. Findings can retain a
shell verification command for later replay, under a trusted-writer model.
**Scenario/hypothesis:** a read-only review acquires post-task memory writes,
or a later session treats a saved verification command as permission to run
it in a new environment. Neither follows merely from wanting accurate recall.
**Counterweight:** Fable's AUTH gate and memory-trust doctrine explicitly say
that documentation is not authorization and fetched/subagent text is data.
No memory poisoning or unauthorized execution was demonstrated here.
**Proposal:** apply the user's effect boundary to the entire task, including
verification, cleanup, memory and session-end. A saved command is a proposed
check, not standing authorization. Preserve the trusted-single-user option,
but make that assumption explicit before generalizing the product.
[S1: Session End; S5: AUTH; S7; S11; S12: cmd_verify; S15]

### LR-07 — Medium: useful heuristics are phrased as universal laws

**Observed:** YAGNI and architecture-simplicity call every single-consumer
abstraction debt, while the architecture skill also requires modules by
reason to change and pure logic separated from I/O. The persona bans hedging,
while AGENTS and Fable require honest uncertainty and low-confidence labels.
**Scenario/hypothesis:** a useful single-consumer parsing boundary is inlined,
or an architectural hypothesis is worded like an observed fact.
**Counterweight:** the anti-framework examples and direct tone solve real
problems. A capable model can distinguish a speculative layer from a useful
boundary, or concise uncertainty from empty hedging. The text should too.
**Proposal:** retain the reason behind each heuristic: present value and
change isolation, not consumer count; calibrated confidence, not confident
wording. Risk depends on consequences, not just lines/files changed.
[S16, S17, S18; S1: reporting]

### LR-08 — Medium: progressive disclosure can remove exceptions as well as detail

**Observed:** runtime compact mode keeps OPS sections 1-5, not Superpowers'
explicit pure-documentation/one-line exceptions. Critical topic detail is
JIT-loaded. The repo's standard `CLAUDE.md` asserts a GitHub-runner context
and skips memory; the general contract assumes persistent memory. Adapters
correctly distinguish file presence from actual activation.
**Scenario/hypothesis:** hosts loading different subsets get different rules,
not merely different levels of detail. A locally loaded runner adapter can
also describe the wrong environment. Actual host loading was not tested.
**Proposal:** keep authorization, uncertainty, stop conditions and applicability
exceptions in the irreducible core. Make adapters declare capabilities and
context explicitly. Trace which procedure/version was actually loaded when
evaluating behavior; a skill-name marker is insufficient.
[S3; S10: When NOT to use; S19; S20; S21]

### LR-09 — High for product claims: process compliance is not causal product benefit

**Reported:** the historical external A/B in README has equal solved-task
counts and higher prompt-token use on matched successes. Raw artifacts are
not bundled. This neither proves equivalence nor disproves usefulness; it
also does not establish a general reliability gain on hard tasks or a
corresponding increase in billed cost. The rejected adaptive-rigor candidate
and the confounded full/thin replay are negative evidence, not optimization wins.
**Observed:** task smoke uses deterministic outcome checks; traps target
method/security adherence; trigger evals target routing; ablation is explicitly
descriptive, with ambient skills uncontrolled. These answer different questions.
**Proposal:** maintain separate claims for health, activation, adherence,
task success, safety and cost. Compare the same host/model on held-out work
before attributing improvement to the kit. Do not remove rules because of
the confounded replay, or claim a cheaper model beats a stronger one from a
method slogan. Retain the project's unusually honest negative-result records.
[S22; S23; S24; S25; S5: opening claim]

### LR-10 — Medium: the learning loop can turn one successful case into a policy

**Observed:** skill-authoring distinguishes reusable procedures from facts
and asks for a trigger check plus replay of one past case. It also warns
against generic skills the model already knows. The usage methodology
separates kit-internal sessions from actual work and installation eras.
**Scenario/hypothesis:** an incident-specific workaround becomes another
mandatory rule and gets validated against the same case that produced it.
**Proposal:** preserve provenance and a candidate state; add at least a
nearby negative case and a held-out case before broad promotion. Retirement
should depend on post-install opportunity/use and outcome contribution, not
raw read counts. This report itself is dated static analysis, not new policy
or proof that its hypothesized failures occurred.
[S26; S27]

## 5. A simpler target contract — proposal, not a new implementation layer

Separate decisions that are currently interleaved:
1. **Authority/effects:** what the user authorized, where, and with what limits.
2. **Task shape:** answer/review, plan-only, change, or explicitly requested probe.
3. **Evidence:** what must be observed and what invalidates existing evidence.
4. **Procedure:** one lead workflow; load domain specifics only when relevant.
5. **Termination:** complete, blocked, or deliberately partial; then stop.
6. **Retention:** opt-in/standing-authorized memory with provenance and scope.

Use a compact shared rule set and a decision table, not another LLM classifier
or a new FAST/STANDARD/HIGH policy. Phase skills should add domain technique,
not reopen authorization, duplicate verification or redefine completion.
Keep explanations of exceptions next to rules so compact loading preserves them.

Minimum evidence record: claim, source/check, scope, checked state, observed
result, unresolved limitation. Minimum memory record: conclusion, source,
project/applicability, date, status and supersession. Reuse existing fields
and tools before adding architecture. Exact schemas need a separate design.

## 6. Discriminating regression scenarios — proposed, not executed

| Scenario | Observable correct behavior |
|---|---|
| Authorized local spike | Investigates without a redundant approval pause; no retained production feature |
| Local change, no git instruction | Follows one declared commit policy; no skill silently expands authority |
| Code wrong, test/spec agree | Fixes under existing authorization; does not demand three-way agreement first |
| One material claim cannot be checked | Labels incomplete evidence; no count-only VERIFIED label |
| Follow-up after unchanged passing test | Cites the checked state; reruns only if something invalidated it |
| Old finding superseded by new decision | Shows supersession and resolves the current applicable conclusion |
| Review-only task finishes | No undeclared write/deploy/memory side effects after the report |
| Single-consumer pure parser | Keeps or removes the boundary for present value, not caller-count dogma |
| Same task on full/compact/runner profiles | Same authorization and honesty invariants despite different capabilities |
| Skill replay plus nearby counterexample | Special-case success does not become a universal rule |

Test behaviors and resulting state, not whether a prescribed phrase appears.
A prompt can contain the right words and still route incorrectly.

## 7. Bounded evidence plan and priorities

**First:** reconcile LR-01/02/03 and carry memory validity into the default
route. These are specific contract questions, not a request to delete discipline.
**Next:** use the scenarios above as a fixed smoke corpus with outcome checks
independent of the candidate's self-report. Record failed and skipped cases.
**Only then:** compare a frozen current kit, a conflict-resolved candidate,
and the same host without kit instructions on held-out external tasks.
Do not mix that policy comparison with a simultaneous memory redesign.

A narrower first product experiment would test memory alone: use fixed
external, two-session task histories with unchanged methodology. Compare the
kit memory engine against ordinary searchable Markdown notes containing the
same facts. Include a superseded decision. In the second session, judge the
actual task result and whether the obsolete decision was avoided; include
write, retrieval, retry and rework costs. Repeat the cases under a predeclared
budget. This isolates memory's contribution from simply having more information;
it says nothing by itself about whether a thin prompt core is safe.

All comparison arms need fresh isolated state, identical task fixtures,
matched tools/model/settings, randomized arm order, preserved outputs, and a
fixed time/tool-call/spend budget with a stop rule. Cross-chat memory needs
its own multi-session cases; a single-session coding benchmark cannot value
it. Control memory exposure separately instead of silently giving one arm
extra task knowledge. Keep provider failures/timeouts as a separate outcome
class; never quietly drop them from the success denominator.

Before any live replay, verify actual OS/tool boundary confinement and no
write access to personal repositories, memory or credentials. A temporary
working directory is not that guarantee. No live experiment was authorized
or run here. The confounded incident gives a concrete reason for this prerequisite.

Measure correct task outcome, false completion, unauthorized effects, user
interruptions, rework, wall-clock time and real provider usage. Trigger rate
and phrase markers remain diagnostics. Predeclare acceptance criteria; a
small smoke study can reject a bad candidate, not prove universal superiority.

## 8. Source index

All paths are relative to the local kit root. Section references above are
preferred to unstable line numbers. These are sources, not instructions to execute.

- S1: `AGENTS.md` — identity, routing, reporting, Session End.
- S2: `OPS.md` — execution lock, phase gates, memory, skills, drift checks.
- S3: `SKILL_RUNTIME.md` — compact/core modes and skill loading.
- S4: `profile.yml` — always_on/domain and adapter declarations.
- S5: `skills/fable-method/SKILL.md` — fit/intent/AUTH/verification/report gates.
- S6: `skills/brainstorming/SKILL.md`; `skills/git-workflow-and-versioning/SKILL.md`.
- S7: `skills/fable-judge/SKILL.md` — claim verification and count verdicts.
- S8: `skills/code-review-and-quality/SKILL.md` — scope/severity definitions.
- S9: `skills/verification-before-completion/SKILL.md` — evidence freshness.
- S10: `skills/superpowers/SKILL.md` — phases, scoped checks, exceptions.
- S11: `skills/dev-wiki/SKILL.md` — save/search and project/global boundary.
- S12: `memory/db-tools/findings.py` — search lifecycle, verification, source fields.
- S13: `memory/db-tools/search_all.py` — default cross-store recall interface.
- S14: `memory/scripts/memory-warmup.py` — uncertainty feed and session bootstrap.
- S15: `skills/security-and-hardening/SKILL.md` — Memory Trust/ASI06.
- S16: `skills/yagni/SKILL.md` — Rules and change filter.
- S17: `skills/architecture-simplicity/SKILL.md` — dependency/module principles.
- S18: `skills/engineering-persona/SKILL.md` — tone and uncertainty language.
- S19: `adapters/UNIVERSAL.md` — mechanisms and activation verification.
- S20: `CLAUDE.md` — runner-specific context and verification.
- S21: `docs/superpowers/specs/2026-09-06-instruction-precedence-calibration-design.md`.
- S22: `README.md` — Evals & Trend Loop; Measured cost; platform caveats.
- S23: `docs/research/2026-09-05-open-source-product-direction.md` — reported evidence.
- S24: `docs/research/2026-09-06-bounded-eval-incident-negative-result.md`.
- S25: `docs/research/2026-09-03-adaptive-rigor-v1-execution-blocker.md` — recorded gate outcome.
- S26: `skills/skill-authoring/SKILL.md` — session-to-skill lifecycle.
- S27: `docs/audit-methodology.md` — internal-use and installation-era confounds.

**Bottom line:** keep the memory, domain knowledge and evidence discipline.
Make their composition coherent, their side effects bounded, and their value
falsifiable on real tasks. This review proposes that direction; it does not
claim it has already improved quality, reduced cost, or fixed the code findings.
