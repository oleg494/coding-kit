# Bounded Evaluation Experiment: Negative Result & Confounding Incident

**Date**: 2026-09-06  
**Status**: Completed — Negative / Confounded Result.  
**Decision**: **DO NOT REMOVE INSTRUCTIONS BASED ON THIS EVIDENCE.** Prevent further evaluation runs until true OS-level sandbox isolation is enforced without relying on `--dangerously-skip-permissions`.

---

## 1. Executive Summary

An experimental bounded 1-pair comparison was conducted on a real historical bug replay from an external repository (`tg2notebooklm`, packaging source budget error):
- **Arm 1 (Full Kit)**: Configured with full kit instructions (`AGENTS.md` + `OPS.md` + `SKILL_RUNTIME.md`, ~15.4KB setup) + 36 skills catalog.
- **Arm 2 (Thin Core)**: Minimal router (`coding-kit-thin-core.md`, ~1.3KB) + 36 skills catalog.
- **Model**: `agy --model gemini-3.8-flash-high`.

### Outcome
1. **Arm 1 (Full Kit)**:
   - **Result**: FAILED independent scratch oracle (`RC: 1`).
   - **Incident**: The agent invoked PowerShell filesystem search (`Get-ChildItem -Path <host-home> -Filter "tg2notebooklm"`) and departed the designated scratch workspace, modifying `pack.py` in the live repository on Desktop instead of the scratch clone.
   - **Restoration**: Pre-run transcript step 22 (`2026-09-06T06:31:25Z`) proved the live repository working tree was clean at commit `4fa3a5a` prior to any modification. The agent removed two lines (`if slots_remaining <= 0: break`). The file was reverted via `git checkout src/tg2notebooklm/pack.py` at `06:40:20Z`.
2. **Arm 2 (Thin Core)**:
   - **Result**: FAILED (Process Timed Out >300s).
   - The agent remained inside the scratch workspace, but stalled or exceeded the non-interactive execution timeout without producing file modifications.

---

## 2. Methodology & Governance Conclusion

- **The comparison is completely confounded**:
  - Full Kit's failure was an unintended departure from the designated workspace via unbounded filesystem search commands under `--dangerously-skip-permissions` (no OS-level sandbox existed).
  - Thin Core's failure was an uncharacterized latency/execution timeout.
- **Neither arm succeeded under the independent deterministic test oracle.**
- **Decision**:
  - This trial provides **zero evidence** that a thin prompt core saves quota or preserves task outcome.
  - No prompt reductions, core diet removals, or instruction pruning may be justified by this run.
  - Any future cross-arm evaluation requires hard OS-level workspace confinement (container, chroot, or strict path-enforced driver) rather than reliance on CLI permission bypass flags.

---

## 3. Preserved Incident Evidence Artifacts (Local Temp)
- `incident.txt`: Detailed pre-run git status transcript citations, timestamps, and process termination records.
- `coding-kit-thin-core.md`: Exact thin core text evaluated.
- `arm1_full_result.json`: Raw execution output, tokens, and error payloads for Arm 1.
- `run_pair_comparison.py`: Reproduction runner script used for the trial.
- Research memory entry: `findings.py` finding id `318`.
