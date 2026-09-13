# Hermes Adapter — coding-kit

> Verified against hermes-agent v0.21.2 (`476a45f4f336`, 2026-09-12). Evidence: [H1 probe matrix](../docs/research/2026-09-13-hermes-h1-evidence.md). This adapter is the ONLY supported kit→Hermes path; the old rsync+manual-SOUL recipe (server skill `coding-kit-maintenance`) must not be used after migration.

## Layout

```
<HERMES_HOME>/kit-skills/coding-kit/<skill>/   # generated projection (37 skills)
<HERMES_HOME>/config.yaml                      # skills.external_dirs += <home>/kit-skills
<HERMES_HOME>/SOUL.md                          # delimited kit routing block only
```

Kit core (`AGENTS.md`, `OPS.md`, `skills/`, `memory/`) is never installed into Hermes; the projection under `kit-skills/` is generated, read-only by convention, and never hand-edited.

Why external root instead of the old local `skills/coding-kit/` copy: the curator's `archive_skill` **really archives** local copies whose names appear in `.bundled_manifest` (verified: 3 kit names collide — `requesting-code-review`, `systematic-debugging`, `test-driven-development` — with `prune_builtins: true`), while external-dir skills are refused by two independent guards. External root also keeps full prompt-index visibility (37/37, category `coding-kit`).

## Install / update

```bash
python scripts/tools/hermes_adapter.py --kit <kit-root> --hermes-home <profile> preview
python scripts/tools/hermes_adapter.py --kit <kit-root> --hermes-home <profile> apply
python scripts/tools/hermes_adapter.py --kit <kit-root> --hermes-home <profile> restore
```

- `preview` (default) is read-only; apply is explicit and idempotent.
- Legacy local `skills/coding-kit/` blocks apply until `--retire-legacy` records its exact preimage in `.kit-hermes-restore.json` and removes it from discovery. No discoverable `.retired-*` directory remains.
- Warnings (bundled-name overlap, local same-name skills) are reported, not blocking: bare-name loads may be refused as ambiguous — use `coding-kit/<name>`.
- Kit updates: re-run `apply` after `git pull`; changed skills are updated, removed kit skills retired, foreign files untouched.

## Behavior contract (local regression evidence: 23 checks)

| Guarantee | Mechanism |
|---|---|
| Preview mutates nothing | read-only `plan()` |
| Apply touches only the 3 owned surfaces | explicit target list; everything else foreign |
| Handled apply failure, including recovery-record persistence → rollback | kit `DeployTransaction` includes both metadata files before commit; rollback errors remain reported |
| `restore` → original owned bytes | format-2 recovery images preserve CRLF, binary files, empty directories and prior absence across updates |
| No-op apply changes nothing | byte-equality check skips identical skills and state rewrite |
| Unrelated sibling files survive | recovery records individual managed skill subtrees, not the complete external root; only previously-owned names are retired |
| SOUL personal text survives | kit block replaced strictly between `<!-- kit:begin v… -->` / `<!-- kit:end -->` markers |
| config.yaml keys/comments survive | surgical `skills.external_dirs` patch (CRLF-tolerant) |

The external root must stay inside the selected profile and outside its local `skills/` tree and kit source. A generated skill subtree is the ownership unit: do not hand-edit inside it. Restore replaces recorded config/SOUL preimages; save later personal edits before restoring. Old recovery formats are rejected without conversion. These are handled-I/O guarantees, not concurrent-write or power-loss durability. Current local checks do not replace a fresh native-Hermes integration drill after the repair.

## Memory routing (SOUL block content)

| Question | Route |
|---|---|
| Past conversation | `session_search` |
| Durable project decision/pitfall | `python ~/.memory/db-tools/search_all.py "<topic>"` (check `[superseded]`/`[unverified]` badges) |
| Procedure | `skill_view coding-kit/<name>` |
| Current config/runtime | owning repo/config, observed process |
| Stable user preference | native MEMORY.md |

Native MEMORY.md is bounded (~2,200 chars) and observed saturating (95–99%): when full, offload durable facts via `findings.py add` instead of compressing by hand.

## Measured limitations (not fixed; no demonstrated harm)

- Rendered descriptions truncate to 60 chars (`...`) in the prompt index; full bodies remain loadable. Revisit only with a demonstrated selection failure.
- `is_curation_eligible` reports True for external bundled-named skills (name-based flag) — write protection is enforced by `archive_skill`'s external guards, not the flag.
- Missing external root is silently skipped by Hermes — `preview`/`apply` validate existence (the root is created inside the profile, so absence means a broken apply).

## H4 live-migration checklist (separate authorization)

1. Backup: `config.yaml`, `SOUL.md`, `skills/coding-kit/` (exact bytes).
2. `preview` → review plan + warnings; `apply --retire-legacy`.
3. Update the server skill `coding-kit-maintenance` so its next `rsync` cannot resurrect the local layout.
4. New session smoke: `skills_list` shows `coding-kit` category; `skill_view coding-kit/ponytail` loads; `search_all.py` reachable.
5. Regression → `restore`, investigate before retry.
