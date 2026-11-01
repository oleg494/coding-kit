# Autonomous supervisor CLI

Read only when running the optional executor/verifier supervisor.

Optional, for continuation across process boundaries (compaction, terminal death):
a foreground stdlib supervisor the skill does not rely on.

```bash
python scripts/tools/autonomous.py --workspace PATH --mission TEXT \
  --executor COMMAND --verify COMMAND \
  [--state-dir PATH] [--max-iterations 10] [--timeout 600] \
  [--handoff FILE]
```

`--handoff FILE` binds a captured handoff (see `scripts/tools/handoff.py`)
into the persisted config: the report is regenerated before every executor
launch and appended to the worker prompt as reinspection context; drift is
never treated as completion, and the independent verifier stays the only
completion gate. Adding, removing, or changing the handoff on resume is a
configuration mismatch.

- **Commands are argv, never shell**: `--executor`/`--verify` are resolved to argv
  without a POSIX shell; Windows `.cmd`/`.bat` wrappers need `cmd`.
- **State**: default `<workspace>/.autonomous`; `state.json` holds config,
  checkpoint, iterations, status, verification feedback; logs in `state-dir/logs/`;
  atomic writes survive a crash. Written before **every** executor launch, iteration
  1 included, so a crash at or before the spawn still resumes. Schema version `1`.
- **Checkpoint contract**: the executor gets the mission and protocol on stdin,
  including `Checkpoint: <absolute-path>`, also exported as env
  `AUTONOMOUS_CHECKPOINT`. `checkpoint.json` is the model's proposal, removed before
  each spawn. Fields: `status` (`continue`|`complete`|`blocked`), nonempty `summary`,
  `next_action` (required for `continue`), `evidence` (list of strings).
- **Checkpoints are claims, not commands**: the supervisor never executes a command
  from model output. `complete` is accepted only after the configured `--verify`
  exits zero; failed verification output feeds the next iteration. `evidence`
  strings are the model's claims — on `continue` only their shape as a list is
  checked, never their truth.
- **Truthful stopping**: nonzero executor exit, missing or malformed checkpoint, or a
  repeated checkpoint report stops instead of looping. The stall detector compares
  the normalized JSON (`status` + `summary` + `next_action` + `evidence`); three
  identical consecutive `continue` **reports** stop the run as stalled. It sees
  repeated *reports*, not absent progress: rewording yields a new signature, while
  `--max-iterations` still bounds each invocation.
- **Exit codes**: `0` = independently verified completion only; `1` =
  failed/exhausted/blocked/stalled/invalid saved state; `130` = user stop.
- **Exhaustion & resume**: hitting `--max-iterations` preserves resumable state and
  exits nonzero — not completion. Resume with the same workspace, mission, executor
  and verifier; durable progress is reused but completion is rechecked against the
  live verifier, and a configuration mismatch is rejected. Unreadable, malformed or
  unsupported saved state (a version other than `1` included) is rejected with a
  one-line stderr diagnostic and exit `1`: the executor never launches and
  `state.json` stays byte-identical, never silently reinitialized.
- **Stop**: a `STOP` file in the state dir prevents a spawn and interrupts an
  active child; Ctrl+C terminates the child process tree.
- **Honest boundaries**: no daemon, installed hook, new dependency, credential
  manager or implicit auto-approval. It launches a user-selected CLI; the harness
  keeps permissions and confinement. **A filesystem workspace is not a security
  sandbox.**
