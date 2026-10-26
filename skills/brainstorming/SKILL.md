---
name: brainstorming
description: 'Use when deciding what to build: a new feature, component or subsystem, a vague or conflicted request, a requirement that spans several capabilities, or a product-level design choice with real tradeoffs. Produces intent, constraints, capability map, spec and observable acceptance. Not for service or module structure (architecture-simplicity), consequential tool selection (production-first-decisions), executing already-specified multi-slice work (writing-plans), or non-code judgment work (fable-method).'
license: MIT
metadata:
  version: "6.0.0"
---

# Brainstorming — from idea to agreed design

This skill decides *what* to build and how we will know it is built. It ends
with acceptance criteria a stranger could check, and with a written spec when
the work needs one. Execution order, slicing and delegation belong to
`writing-plans`.

Understand the requested outcome, inspect existing patterns, choose a complete
solution, and continue into implementation when that is what the user asked.
Authorization and stop conditions come from OPS §1, not the design phase.

## Choose the necessary design depth

- **Investigation/spike:** answer a feasibility question with a bounded probe.
  Define what the probe measures, run it, report evidence and limitations.
  Do not silently turn a requested investigation into a permanent feature.
- **Bounded change:** trace the existing flow and affected callers, resolve
  details from code, state the approach briefly, implement and verify.
- **Architectural change:** map responsibilities, interfaces, state transitions,
  compatibility and failure handling before code.
- **Multi-capability requirement:** one request bundles several independently
  testable capabilities (accounts, billing, notifications). Write a capability
  map before a spec, because the map decides build order and what can be
  delivered in parallel:

  ```markdown
  # Capability Map: [Initiative]
  | Module id | Responsibility | Depends on |
  |---|---|---|
  | identity | Accounts, sessions, SSO | — |
  | billing | Plans, invoices, payments | identity |
  | notifications | Email and webhook fan-out | identity |
  ```

  Build order: identity → billing, notifications. Each capability gets its own
  acceptance criteria; all requested capabilities are delivered, not just the
  first sub-project.

Complexity determines design depth, not permission. Reclassify when new facts
change the approach; no mandatory heavier-path tie-break or approval pause.
Plan/design-only requests stop at their requested deliverable.

## Design workflow

1. **Inspect context.** Read the relevant implementation, configuration and
   existing decisions. Reuse project conventions rather than adding a parallel
   design. Do not ask the user for repository-provided information.
2. **Define done.** Capture required behaviors, compatibility, constraints,
   excluded work and observable acceptance. Reframe a vague goal as checks
   before designing anything:

   ```
   REQUEST: "Make the dashboard faster"
   DONE WHEN: LCP < 2.5s on a throttled 4G profile
              initial data load < 500ms
              CLS < 0.1 during load
   ```

   A simpler implementation must still deliver all requested formats, paths,
   error behavior and quality.
3. **Resolve uncertainty.** Decide ordinary details from evidence and explain
   consequential defaults. When something about intent is genuinely missing,
   ask one batch of related questions, most important first: one open,
   description-first question ("walk me through the last time this hurt you?",
   "what would make you wince if I got it wrong?"), then the concrete
   specifics you need. Offer a short menu of options only when the user is
   stuck or asks what you think. Ask only when an unavailable answer would
   materially change the outcome or an action lacks authority, and keep
   independent authorized work moving while you wait.
4. **Compare real alternatives.** Include alternatives only when they have
   meaningful tradeoffs. Prefer the simplest complete approach; do not invent
   options to fill a quota. Existing proven patterns may settle the decision.
5. **Design the change.** Cover components, data flow, errors, integration,
   migration and verification at the depth needed. Separate units by reason
   for change, keep concrete interfaces, avoid unrelated restructuring.
   Consequential platform, language, library or medium choices rest on repo
   defaults and existing patterns where they exist; when you choose one the
   user has not stated, own it as your call in plain words, never record it
   as something the user agreed to, and surface it early enough to correct
   cheaply.
6. **Check the design.** Resolve contradictions, placeholders, missing required
   paths and uncertain boundaries. Map acceptance to checks before coding.
   For a complex design, also read it as a builder who cannot ask you anything
   and collect only the points where a wrong guess would change what gets
   built — skip wording nitpicks and anything the design explicitly leaves to
   the builder. Use an available reviewer when independent perspective is
   useful and host rules permit it; otherwise do the check yourself.
   Answer the answerable from evidence and mark those calls as yours; add the
   genuinely user-owned questions to the same batch as step 3. A bounded change
   needs little or none of this.
7. **Continue.** Use `writing-plans` when the execution shape is non-obvious,
   then implement and verify without asking the user to approve the same
   authorized work again.

   When intent was unclear, briefly reflect what the thing is for and who it
   serves before committing to a design. Separate the user's statements from
   your assumptions. Accept corrections; do not defend an earlier reading.

## The spec

Reuse an existing spec or the user's explicit acceptance criteria. Write only
the design that is missing, at the size the work needs — a bounded change
needs a paragraph in the task tracker, not a document.

**State assumptions, then proceed.** Surface the ones you are betting on and
which would be expensive to reverse:

```
ASSUMPTIONS:
1. Web app, not native mobile
2. Session cookies, not JWT
3. PostgreSQL already provisioned
```

Proceed on those unless one changes the outcome the user asked for or the
authority required for it — those two are worth a question; the rest are not
worth a pause. Record them where the work is tracked so a later reader can
reject them.

**Spec template** — keep the sections that decide something, drop the rest:

```markdown
# Spec: [Project/Feature]

## Objective
What we're building, why, who uses it; user stories or acceptance criteria.

## Commands
Build, test, lint, dev — full commands as they actually run.

## Tech stack and structure
Framework, language, key dependencies with versions; directory layout with
one-line descriptions of the parts a newcomer must find.

## Code style
One representative snippet plus the conventions it shows.

## Testing strategy
Framework, test locations, level of tests, what gets covered.

## Boundaries
- Always: verify affected behavior, follow project conventions, validate
  trust boundaries
- Ask first: missing authority for irreversible or outward actions, or
  unavailable information that changes the outcome
- Never: expose secrets, mutate production data as a test, suppress a real
  failure

## Success criteria
Specific, testable conditions — each mapped to a check.

## Open questions
Only what is genuinely the user's to decide, with your recommended default.
```

Update the spec when decisions or scope change, not to keep it in sync with
every line of code. Save it durably when requested or when an explicit project
workflow requires it; otherwise the task tracker or chat is enough.

## Artifacts and review

Reuse the project's existing design-document location; if none exists and a
durable file is needed, use `docs/design/YYYY-MM-DD-<topic>-design.md`. A
design file need not contain the whole implementation; record enough for
another engineer to understand decisions, contracts and acceptance.

User review is a gate only when the user requested it or a real project
approval governs the action. Do not ask after every section, force spec-file
approval, or end with an execution-method menu when implementation is already
authorized. Commits follow OPS §1.

## Failure patterns

- New subsystem treated as new authorization: design thoroughly, then execute.
- Missing info guessed despite incompatible outcomes: inspect, then ask.
- Local security fix stalled solely because it touches auth: fix with isolated
  positive and negative checks; no production mutation implied.
- Scope or platform silently drifted: "build a CLI" became a web app, or a
  report became a dashboard, without the user's word or a stated assumption
  they could reject.
- An unstated consequential default (language, library, medium) recorded as
  if the user had chosen it: a default they never heard is one they could
  not reject; own it in plain words instead.
- CSV-only shipped when CSV and JSON were requested: incomplete, not minimal.
- Coding started before acceptance or any check existed.
- Requested features dropped as an "MVP", or unrequested ones added because
  they seemed useful.
- A spec document demanded, a human signoff awaited, or another menu offered
  for work already authorized.
- A procedural skill says stop: reconcile it with scope and authority; do not
  leave reachable implementation undone or ignore an explicit user stop.

## Developing the user's thinking

When the request is an unfinished idea ("I want X but not sure what", "help me
find directions"), do not demand a finished specification or choose their goal
for them. Start with the description-first question above. When they ask for
directions or need concrete examples to react to, offer two to four
meaningfully different interpretations with consequences; keep them as
proposals, not decisions already made for the user.

When the user states an unusual method with explicit constraints (hardware,
scale, policy), evaluate it against those constraints before recommending the
standard approach; if it satisfies them, work within it and name only the risks
the stated constraints do not cover.

The user's goal stays theirs: if they correct your interpretation of what they
want, adopt the correction and continue from it; do not re-propose the
rejected framing under a new name.

## Check before you leave design

- [ ] Required behavior, constraints and important risks are explicit.
- [ ] Success criteria are observable and each is mapped to a check.
- [ ] Multi-capability work has a capability map with build order.
- [ ] Necessary user decisions are resolved; ordinary details follow repo
      conventions and are recorded as your calls.
- [ ] No open question is an approval request for already authorized work.

---

Source: obra/superpowers (MIT); spec-driven development absorbed from
obra/superpowers and coding-kit v5.1. Adapted for coding-kit.