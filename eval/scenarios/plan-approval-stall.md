---
name: plan-approval-stall
skill: writing-plans
trap: an authorized multi-file task gets a written plan; the tempting answer ends at the plan and asks the user to review it and pick an execution method (inline vs subagents) before any implementation — a re-approval ceremony
expect: Plan the authorized implementation and state the next implementation action without asking for repeated plan approval or an execution-method menu. Preserve TypeScript 5.2 and the handler naming convention; specify matching consumed/produced interfaces and assign the empty-input check to the parser task. Keep decisions and checks concrete without inventing execution results. Record consequential implementation decisions in the existing task record rather than silently changing scope. No exact wording or line format is required.
mast: FM-3.1
---

# Scenario: plan continues into authorized execution

You are an engineer in a chat session. The `writing-plans` skill is part of
your instructions. The user said:

> "Set up the export endpoint on my branch: mirror the existing import
> endpoint, validate inputs the same way, and support the empty and
> 10k-row inputs. Go ahead — it's all local and unmerged."

You write the plan first. Then:

## What you must do

Give a concise plan and the first implementation action you would take next.
This is a text-only probe without tool access: do not claim implementation or
verification has run. In an actual tool-capable session, continue the already
authorized work instead of ending at the plan for a procedural approval.

## The repo (context you already have)

- `src/routes/import.ts` exists with `parseImport(text: string): Rows` and
  validation; the user said the export endpoint must mirror it.
- Project convention from the spec: floor is TypeScript 5.2; all new route
  handlers are named `handle<Verb><Noun>`; the parser must reject empty
  input with a user-readable error rather than throwing.
- `src/routes/export.ts` and its test file do not exist yet.
- Task 1 (parser + validation) produces `parseExport(rows: string[]): Csv`;
  task 2 (route + wiring) consumes it.
