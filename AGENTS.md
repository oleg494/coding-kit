# coding-kit — Agent Router

Read [OPS.md](OPS.md) once per session, unless its current content is already
loaded. OPS.md is the canonical contract for authorization, completion,
evidence, skill loading and memory. This router adds no second workflow.

Answer in the user's language. Keep implementation and shared documentation
in English. Host system/developer instructions take precedence; kit skills
never expand the user's authority or override a stop/read-only request.

Load a skill only for an explicit invocation or an unresolved domain question;
see descriptions in `skills/`. Do not load the full method chain at startup.
Memory is retrieved when prior decisions matter, not warmed up on every task.

An optional `.override.md` beside this file may select
`MODE: EXPLORATORY_PROTOTYPE` (bounded hypothesis probes; verify before
integration) or `MODE: STRICT_AUDIT` (findings only, no edits). Neither mode
grants external, destructive or spending authority.
