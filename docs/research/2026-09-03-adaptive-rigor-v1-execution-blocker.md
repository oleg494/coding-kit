# Adaptive Rigor v1 — live A/B execution blocker & unblock path (2026-09-03)

Status: **the `claude-*`/`antigravity-local` model arms remain BLOCKED
upstream at the proxy; the benchmark infrastructure itself is UNBLOCKED via
the verified `dashscope-*` Claude Code gateway pool.**
Spec: `docs/superpowers/specs/2026-09-03-adaptive-rigor-v1-design.md`.
Gate: `eval/rigor/gate.py` (unit-verified on synthetic documents: ACCEPT /
REJECT / KEEP_BASELINE / ACCEPT_WITH_WARNINGS paths, partial-coverage
rejection). Runner: `eval/rigor/runner.py` (dry-run green; live smoke
executed end-to-end but every executor call was rejected upstream).

## Observed failure

Every Claude Code CLI invocation (2.1.220) against either configured
Anthropic-compatible endpoint fails at the proxy with:

```
API Error: Request rejected (429) · All N attempted keys for provider
'antigravity-local' failed to process the request.
```

The CLI then retries with backoff (11 attempts), which presents as a hang.
Endpoints tested: `https://mproxy.online` (key vk-…, 1 key) and
`https://multiproxy.root.sx` (key oleg_…, 2 keys via `--settings` env
override). Both route CLI traffic to the same broken `antigravity-local`
upstream pool.

## Evidence: synthetic probes pass, CLI traffic dies

Direct `POST /v1/messages` probes (urllib/curl) against mproxy.online, all
HTTP 200 unless noted:

| # | probe | result |
|---|-------|--------|
| 1 | plain messages, claude-sonnet-4-6 | 200 pong |
| 2 | plain messages, claude-opus-4-6-thinking | 200 pong |
| 3 | stream=true | 200 stream |
| 4 | system[] + cache_control ephemeral | 200 |
| 5 | tools[] (1 tool) | 200 |
| 6 | 16KB system text | 200 |
| 7 | anthropic-beta claude-code-20250219 | 200 |
| 8 | anthropic-beta interleaved-thinking | 200 |
| 9 | anthropic-beta context-management | 200 |
| 10 | anthropic-beta prompt-caching | 200 |
| 11 | User-Agent claude-cli/2.1.220 | 200 pong |
| 12 | 60 tools, 178KB payload | 200 |
| 13 | metadata.user_id | 200 |
| 14 | output_config json_schema | 200 |
| 15 | max_tokens=64000 / context_management / speed / tools=[] | 200 |
| 16 | FULL CLI-shaped combo (stream+system cache+60 tools+metadata+betas+UA) | 200 stream |
| 17 | x-stainless-* SDK header block | 200 pong |
| 18 | model `claude-sonnet-4-6[1m]` | 400 unsupported (not the trigger) |

CLI variants, all failing with the 429/502 `antigravity-local` error:

- default profile, model claude-sonnet-4-6 (mproxy and multiproxy);
- `--tools ""`, `--safe-mode`, `--no-session-persistence`;
- `--system-prompt "minimal"`;
- `--bare` (no MCP servers, no plugins);
- `--settings` override to multiproxy.root.sx (key count changed 1→2,
  proving the override applied; routing failure unchanged);
- gemini-3.8-flash (provider key error on the same pool).

Debug capture (`claude --debug-file`, committed at eval/results/cli-debug.log,
secrets-verified: Authorization values are `[REDACTED]` by the CLI):
`[API REQUEST] /v1/messages source=sdk` → attempt 1/11 429
`antigravity-local` within 8s; subsequent attempts 502/429 on the same pool.

## Conclusion

The routing rule is proxy-side and keyed on request properties only the real
Claude Code SDK emits (not reproduced by 17 synthetic shape/header probes,
including the full combination). It is not fixable by request shaping from
this repo. The same upstream pool serves both configured endpoints, so no
endpoint switch helps.

## Impact on the acceptance gate

Conditions 1–5 require live executor attempts; none can be recorded while
every CLI request is rejected upstream. Per spec §Error handling, provider
failures are reruns, not task failures — but an executor that cannot complete
any request yields no attempts at all, so the run is incomplete, not a
candidate verdict. Conditions 6–7 measured now:
- cond-6 history: first candidate commit 274fdbc measured 26795 bytes vs
  baseline 26449 (+346, FAIL); OPS §3 compression landed 1386ca4 at
  26444 bytes <= 26449 (PASS). Baseline bundle hash 5295a47f6c2a… reproduced
  from git on every dry run.
- cond-7 PASS: 645 passed / 1 skipped / 76 subtests (full pytest), doctor
  14/14 GREEN, file-size gate rc=0 (hard 0), integrity manifest 141 files,
  skills-sync green — all re-run in the worktree after the compression.
  Note: the worktree's doctor shows skills-sync RED by design after the
  live mirrors were restored to v4.1.0 (see Rollout state below); cond-7
  evidence above was taken before that restore, and the main checkout's
  doctor is GREEN with mirrors at v4.1.0.

## Rollout state

Gate not passed → no cutover. Live mirrors (~/.claude, ~/.agents, ~/.zcode,
repo .agents/skills) were restored to baseline v4.1.0 via
`python scripts/tools/deploy.py` from the main checkout on 2026-09-03;
the candidate policy lives only on branch `feature/adaptive-rigor-v1`.

## Delivered improvements to the harness

- `eval/rigor/` measurement infrastructure: runner (controlled profile,
  per-model arms, attempts, traps with distinct judge, neutral cwd, provider
  retry, stdin prompt passing, triple route repetitions), gate evaluator,
  isolation/canary probes, policy bundle hashing.
- Acceptance gate hardened against vacuous passes: enforces exactly two
  matching model arms, `controlled=True` on every arm, complete microtask
  coverage (<=2 attempts), complete trap coverage, and >=3 repetitions for
  all 10 route cases. Verified by `tests/test_rigor_gate.py`.
- Corpus: 5 microtasks with mutation-tested verifiers, 10 route cases,
  10 named legacy traps wired.
- Candidate policy bundle (commit 1386ca4): superpowers/AGENTS/OPS tiers
  FAST/STANDARD/HIGH_ASSURANCE; OPS.md 138 lines; doctor 14 GREEN; full
  pytest green (645 passed) after the cond-6 compression.
- Baseline pin `b2b495a4` bundle hash 5295a47f6c2ab0b74c08fc7c7e688a482da0a81caa6b226d58b1d92fd4f3e2b7
  reproduced from git on every dry run.
## Unblocked execution procedure

The live benchmark must run on endpoints that route to live provider pools,
such as the verified gateway models `dashscope-glm-5.2-fast-preview` and
`dashscope-deepseek-v4-pro-0813`, judged by an independent model:

```bash
python eval/rigor/runner.py --arm baseline --ref b2b495a4e6cdb8ecfd9450b5812feff8cc82f6f1 \
  --executor "claude" \
  --models dashscope-glm-5.2-fast-preview,dashscope-deepseek-v4-pro-0813 \
  --judge "claude" --judge-model dashscope-qwen3.8-max-0902 --json auto

python eval/rigor/runner.py --arm candidate --ref 1386ca4 \
  --executor "claude" \
  --models dashscope-glm-5.2-fast-preview,dashscope-deepseek-v4-pro-0813 \
  --judge "claude" --judge-model dashscope-qwen3.8-max-0902 --json auto

python eval/rigor/gate.py --baseline <base.json> --candidate <cand.json> --harness-green
```
