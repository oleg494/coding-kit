# Adaptive Rigor v1 — live A/B execution blocker (2026-09-03)

Status: **live A/B runs BLOCKED by provider-side routing; benchmark and
candidate policy delivered as the spec's pre-gate deliverable.**

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

Debug capture (`claude --debug-file`, retained in eval/results/cli-debug.log,
gitignored): `[API REQUEST] /v1/messages source=sdk` → attempt 1/11 429
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

- cond-6 PASS: candidate policy bundle 26444 UTF-8 bytes <= baseline 26449
  (candidate commit 1386ca4; baseline bundle hash 5295a47f6c2a… reproduced
  from git on every dry run).
- cond-7 PASS: 645 passed / 1 skipped / 76 subtests (full pytest), doctor
  14/14 GREEN, file-size gate rc=0 (hard 0), integrity manifest 141 files,
  skills-sync green — all re-run after the cond-6 compression commit.

## Delivered despite the blocker

- `eval/rigor/` measurement infrastructure: runner (controlled profile,
  per-model arms, attempts, traps with distinct judge, neutral cwd, provider
  retry), gate evaluator, isolation/canary probes, policy bundle hashing.
- Corpus: 5 microtasks with mutation-tested verifiers, 10 route cases,
  10 named legacy traps wired.
- Candidate policy bundle (commit 1386ca4): superpowers/AGENTS/OPS tiers
  FAST/STANDARD/HIGH_ASSURANCE; OPS.md 138 lines; doctor 14 GREEN; full
  pytest green (645 passed) after the cond-6 compression.
- Baseline pin `b2b495a4` bundle hash 5295a47f6c2ab0b74c08fc7c7e688a482da0a81caa6b226d58b1d92fd4f3e2b7
  reproduced from git on every dry run.

## Retest procedure when the proxy is fixed

```
python eval/rigor/runner.py --arm baseline --ref b2b495a4e6cdb8ecfd9450b5812feff8cc82f6f1 \
  --executor "claude" --models claude-sonnet-4-6,claude-opus-4-6-thinking \
  --judge "claude" --judge-model claude-opus-4-6-thinking --json auto
# same for --arm candidate --ref <candidate commit>, then:
python eval/rigor/gate.py --baseline <base.json> --candidate <cand.json> --harness-green
```

One-line health check before relaunching:
`claude -p pong --model claude-sonnet-4-6 --tools "" --no-session-persistence`
must print `pong` instead of the antigravity-local 429.
