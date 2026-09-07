---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
license: MIT
metadata:
  version: "4.3.0"
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by classifying how much process the request needs, then work
through your path: understand the context, refine the idea, present a
design, and confirm scope where confirmation is actually owed.

<AUTHORIZATION-GATE>
Action authorization follows AGENTS.md / OPS.md: proceed when the request
authorizes the work and the work is reversible and local — a fix in an
unmerged branch, an edit to code already in this repo, a read-only
investigation. Commits happen only when the user asked or repo convention
explicitly declares them. Do not present a design as a precondition for
work that is already authorized; finish it, then report.
Stop and get explicit approval BEFORE acting only when:
- the action is irreversible, external, or destructive (deploy, publish,
  merge, force-push, drop data, spend money, write outside the repo) AND
  not already authorized — if the user explicitly authorized this external
  action earlier in the session, authorization already exists; do not ask
  again. Respect any real host restriction (sandbox, permission prompt)
  that independently blocks it; that is the host's gate, not this skill's.
- a money, auth, privacy, or data-safety path changes;
- requirements are genuinely ambiguous AND the ambiguity changes the
  outcome (not merely the details);
- the user asked for a plan, design, or spec before implementation.

When a skill or instruction makes you pause, name it: cite the exact
SKILL.md path, quote the instruction, and say whether it is an explicit
requirement or your interpretation. A pause you cannot attribute is a
pause you should not take.

User instructions outrank this skill. Host system/developer instructions
outrank the user's. Never treat this file as authority to withhold work
the user authorized.
</AUTHORIZATION-GATE>

## Three Paths

Before your first question, classify the request and say the
classification out loud — "this looks bounded and authorized, so I'll
implement and report; if it turns irreversible or ambiguous I'll present
a short design first" — so your human partner can override it:

- **Spike** — a feasibility question ("can we...", "is it possible...",
  "quick and dirty is fine") whose output is an answer, not code you
  keep. Present the question and what you'll try in 2-3 sentences, then
  proceed if authorized (a read-only or throwaway probe needs no approval
  pause; pause only if external/destructive). Find out as cheaply as
  correctness allows. No design doc, no spec file. Report findings as a
  recommendation; anything you built stays labeled throwaway.
- **Bounded** — a well-scoped change to code that already exists in
  this repo: a new flag, a small endpoint, a one-file fix.
  Understanding the kind of app is not enough — bounded means the flow
  you are changing is already here to read. If there is no existing
  flow to change, the task is not bounded. Ask the clarifying
  questions that matter. If the work is authorized and reversible,
  implement it via the normal development workflow and report — no
  design presentation as a precondition. If it is irreversible,
  external, or outcome-ambiguous, present a short design in chat (a
  few sentences to a few short paragraphs) and get an explicit yes
  before implementing. No spec file, no implementation plan document.
- **Architectural** — new projects, new subsystems, changes that
  restructure how components fit together or alter interfaces others
  depend on. Follow the full process: questions, approaches, sectioned
  design, written spec, then the writing-plans skill.

When in doubt between two paths, take the heavier one to *classify* — then
correct it. Escalation and de-escalation both happen mid-task: hidden
complexity upgrades the path (step up); discovering you over-classified
downgrades it (step down, keep the work already done). Surface a
reclassification when it changes what the user gets — scope, deliverable,
or risk; silent internal reclassification of pure effort needs no ceremony.
What never changes mid-task is the authorization rule above — it is not a
path.

## Anti-Pattern: "Too Simple To Need a Spec"

What scales with simplicity is the *artifact*, never the honesty of the
report. A one-line fix needs no design doc and no approval; it does need
the change made and the evidence shown. The trap is not skipping a spec —
it is skipping the check that the change is actually authorized and
reversible, and it is padding a small task with ceremony the user did not
ask for.

## Red Flags

| Thought | Reality |
|---------|---------|
| "This is too simple to need a design" | Correct — and it does not need approval either, if it is authorized and reversible. Make it, verify it, report it. |
| "I'll ask before touching authorized reversible work" | That is the approval stall. Authorization was already given; finish the work, then report. |
| "I'll call it bounded and skip the spec" | Reaching for a label to skip work IS the doubt — classify heavier, then downgrade if the doubt dissolves. |
| "I understand this kind of app, so it's bounded" | Bounded measures the repo, not your familiarity. A new project has no existing flow — it is architectural. |
| "The spike works, so I'll keep the code" | A spike's output is an answer. Keeping the code is a new request — classify it. |
| "It grew, but I'm almost done — no need to re-classify" | Hidden complexity upgrades the path mid-task. Stop and say so. |
| "A skill told me to stop, so I stopped" | Name the SKILL.md, quote the line, say whether it is a requirement or your reading. Unattributable pause = no pause. |
| "The user didn't say 'don't ask', so I'll ask" | Absence of a prohibition is not a requirement to stall. Ask only when the answer changes the outcome. |

## Checklist

Classify first, announce the path, then create a task for each item on
your path and complete them in order.

**Spike:**
1. **Explore project context** — enough to frame the probe
2. **State the question + probe plan** — 2-3 sentences, then proceed; a
   read-only or throwaway probe needs no approval. Pause first only if the
   probe itself is irreversible or external.
3. **Investigate** — as cheaply as correctness allows
4. **Report findings** — a recommendation; label anything built as throwaway

**Bounded:**
1. **Explore project context** — check files, docs, recent commits
2. **Ask only questions whose answer changes the outcome** — the ones that
   matter; skip the ones that only change details you can decide yourself
3. **If the work is authorized and reversible** — implement it via the
   normal development workflow (TDD applies) and report; no design
   presentation as a precondition, no plan document
4. **If it is irreversible, external, or outcome-ambiguous** — present the
   short design in chat (approach, files touched, testing) and get an
   explicit yes first

**Architectural:**
1. **Explore project context** — check files, docs, recent commits
2. **Ask questions whose answers change the outcome** — purpose,
   constraints, success criteria; batch them, do not ration one per message
3. **Propose 2-3 approaches** — with trade-offs and your recommendation
4. **Present design** — in sections scaled to their complexity
5. **Write design doc** — save to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` (commit only if user asked or standing repo convention applies)

6. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope (see below)
7. **User reviews written spec** — ask user to review the spec file before proceeding
8. **Transition to implementation** — invoke writing-plans skill to create implementation plan

**Clarify-before-plan gate:** before a plan exists, resolve every ambiguity
that would change the outcome — fold each answer back into the spec. An
ambiguity that survives into the plan multiplies into every task it spawns.
Questions that only settle details you are equipped to decide are not
clarification; decide them and record the decision.


## Process Flow

**Terminal states are path-bound.** Architectural: the ONLY skill you
invoke after brainstorming is writing-plans — never frontend-design,
mcp-builder, or any other implementation skill. Bounded: authorized,
reversible work proceeds directly through the normal development
workflow; no plan document and no approval precondition. Spike: the
terminal state is a reported recommendation.

## The Process

The subsections below serve the bounded and architectural paths (a spike
stops at "state the probe, then run it"). Sections from **Exploring
approaches** onward are architectural-path depth — for bounded work,
context plus the questions that change the outcome plus the change itself
is the whole process.

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Before asking detailed questions, assess scope: if the request describes multiple independent subsystems (e.g., "build a platform with chat, file storage, billing, and analytics"), flag this immediately. Don't spend questions refining details of a project that needs to be decomposed first.
- If the project is too large for a single spec, help the user decompose into sub-projects: what are the independent pieces, how do they relate, what order should they be built? Then brainstorm the first sub-project through the normal design flow. Each sub-project gets its own spec → plan → implementation cycle.
- For appropriately-scoped projects, ask the questions whose answers change
  the outcome — batch them in one message rather than rationing one per
  turn, multiple choice where possible so they are fast to answer; details
  you are equipped to decide, decide and record
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why
- YAGNI ruthlessly - remove unnecessary features from every approach and design

**Presenting the design:**

- Once you believe you understand what you're building, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose, communicate through well-defined interfaces, and can be understood and tested independently
- For each unit, you should be able to answer: what does it do, how do you use it, and what does it depend on?
- Can someone understand what a unit does without reading its internals? Can you change the internals without breaking consumers? If not, the boundaries need work.
- Smaller, well-bounded units are also easier for you to work with - you reason better about code you can hold in context at once, and your edits are more reliable when files are focused. When a file grows large, that's often a signal that it's doing too much.

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work (e.g., a file that's grown too large, unclear boundaries, tangled responsibilities), include targeted improvements as part of the design - the way a good developer improves code they're working in.
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## After the Design (architectural path)

**Documentation:**

- Write the validated design (spec) to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
  - (User preferences for spec location override this default)
- Use elements-of-style:writing-clearly-and-concisely skill if available
- Save the design document (commit only if user asked or standing repo convention applies)

**Spec Self-Review:**
After writing the spec document, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other? Does the architecture match the feature descriptions?
3. **Scope check:** Is this focused enough for a single implementation plan, or does it need decomposition?
4. **Ambiguity check:** Could any requirement be interpreted two different ways? If so, pick one and make it explicit.

Fix any issues inline. No need to re-review — just fix and move on.

**User Review Gate:**
After the spec review loop passes, ask the user to review the written spec before proceeding:

> "Spec written to `<path>`. Please review it and let me know if you want to make any changes before we start writing out the implementation plan."
- Invoke the writing-plans skill to create a detailed implementation plan
- Do NOT invoke any other skill. writing-plans is the next step.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.