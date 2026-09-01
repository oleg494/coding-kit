# coding-kit Evolution Roadmap (v3.5 → v4.0) Implementation Plan

> **For agentic workers:** implement this plan task-by-task with per-task
> checkpoints; for parallelizable tasks use `dispatching-parallel-agents`.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 18 adversarially-verified gaps from the 2026-09-01 SOTA
sweep (findings #181) in 6 independently-shippable waves: security trust
surface, verifier integrity, standards conformance, context hygiene, devflow
gates, observability interchange.

**Architecture:** Every wave is a kit release (minor bump). Each task follows
superpowers (red test → minimal impl → verify → commit) and lands inside
existing structures: doctor checks are `tuple[bool, str]` functions in
`scripts/doctor.py` + a row in `main()`'s `checks` list; eval scenarios are
markdown files in `eval/scenarios/`; scoring changes extend the schema-v1
results store append-only. No new runtimes, no daemons, no pip deps.

**Tech Stack:** Python 3.11 stdlib (json/sqlite3/hashlib/re/pathlib),
pytest, git. Windows-first.

**Spec:** `docs/research/2026-08-24-harness-sota-research.md` (prior wave),
findings #181 (2026-09-01 sweep, session artifact `local://sweep-confirmed.json`).

## Global Constraints

- Python stdlib ONLY. No pip installs, no vendored heavy deps. Clone-and-run.
- Windows 11 Home first: no Windows Sandbox (Pro-only), no Docker/WSL
  requirement. Canonical Home-safe sandbox reference: OpenAI Codex
  synthetic-SID + write-restricted token writeup.
- Thin kit: runtime (LLM, tools, subagents) belongs to harnesses.
- FILE-SIZE gates: code 500/1000, docs 300/500 lines. Every new doc lands
  under 300 or splits.
- Claim discipline: every wave's CHANGELOG entry cites its regression tests
  by name; a claim without a check is not a claim.
- Append-only where history matters: results store (schema-v1), manifests
  regenerated via explicit `--update` (pattern: `file_size_baseline.json`).
- Release contract per wave: bump VERSION + profile.yml together
  (doctor `check_versions`), full `python -m pytest tests/ -q` green,
  `python scripts/doctor.py` green, `ruff` at baseline.

---

## Wave map (each wave = one release; detail in its own plan file)

- **Wave 1 — v3.5.0 trust-surface** — Security triad (OWASP map, CBSE manifest, ASI06 memory defense) + backup/DR → `2026-09-01-wave1-v3.5.0-trust-surface.md`
- **Wave 2 — v3.6.0 honest-oracle** — Verifier integrity: impossible canaries, clean-pass accounting, MAST labels → `2026-09-01-wave2-v3.6.0-honest-oracle.md`
- **Wave 3 — v3.7.0 standards-conformance** — Agent Skills spec, evals.json co-location, canonical skills dir, lifecycle → `2026-09-01-wave3-v3.7.0-standards-conformance.md`
- **Wave 4 — v3.8.0 context-hygiene** — OPS diet / path-scoped rules, compaction eval, Wiki hygiene taxonomy → `2026-09-01-wave4-v3.8.0-context-hygiene.md`
- **Wave 5 — v3.9.0 devflow-gates** — spec-kit gates, Cloudflare review protocol, materiality gate → `2026-09-01-wave5-v3.9.0-devflow-gates.md`
- **Wave 6 — v4.0.0 interchange** — OTel semconv names, ATIF export, transcript normalization → `2026-09-01-wave6-v4.0.0-interchange.md`

## Deferred (explicit non-goals this roadmap)

- ADAS-style meta-agent harness search — until Waves 1-6 metrics accumulate.
- SkillOpt-gated stdlib SKILL.md rewriter (replaces MIPROv2; dspy violates
  stdlib) — after Wave 3 per-skill evals make hold-out splits meaningful.
- AST10 signing (AST01) — no key infrastructure for one user; hash
  manifest (Task 2) is the compensating control.
- ATIF `token_ids`/`logprobs`; OTel runtime export; vector/graph memory
  (Mem0's own paper: ~2% over base; kit has no latency problem).

## Scheduling note

~110 h total. Waves 1-2 are the risk-reduction pair (security + honest
metrics) and unblock trustworthy data for Waves 3-6; do them first and in
order. Waves 3/4/5 are independent of each other — parallelizable by task
batch. Wave 6 last (consumes the schemas the earlier waves stabilize).
