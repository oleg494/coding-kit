# Security map — OWASP ASI/AST10 → kit controls

Every risk from the OWASP Top 10 for Agentic Applications (ASI01–ASI10,
released 2025-12-09) and the OWASP Agentic Skills Top 10 (AST01–AST10,
v1.0 2026-03), mapped to the kit control that addresses it. A control is a
doctor check, a trap scenario, an OPS.md rule, or an explicit
"harness-owned" admission. This is the kit's named security checklist:
when a new control lands, update its row here.

Control planes (verified 2026-09-01):

- **doctor** — `scripts/doctor.py`, all registered checks, exit 1 on any
  failure (`python scripts/doctor.py`; the summary prints the live count).
- **integrity manifest** — `scripts/tools/integrity_manifest.py` +
  `integrity-manifest.json` (wave1 Task 2): SHA-256 over every kit file
  that executes or steers automatically; deploy refuses to copy on drift.
- **trap scenarios** — `eval/scenarios/*.md`, 26; scored by
  `eval/runner.py` with a judge prompt.
- **OPS.md** — the always-loaded contract every harness reads first.

## ASI — Top 10 for Agentic Applications

| ID    | Risk                                 | Kit control (wave1) |
|-------|--------------------------------------|---------------------|
| ASI01 | Agent Goal Hijack | OPS §§1–2 preserve the user's goal, authority and task boundary; hijack-resistance scenarios exercise these rules. Methodology is not a sandbox. |
| ASI02 | Tool Misuse and Exploitation | `shell-injection` scenario; OPS §1 action authorization; destructive-command details in `git-workflow-and-versioning`; host permission gates. |
| ASI03 | Identity and Privilege Abuse | Host-owned identity/credentials; OPS §1 restricts privileged and outward actions to explicit authorization. |
| ASI04 | Agentic Supply Chain Vulnerabilities | integrity manifest (Task 2): SHA-256 over the kit control plane, doctor + deploy enforcement; doctor `check_skill_supply_chain` (license hygiene). |
| ASI05 | Unexpected Code Execution (RCE)      | harness permission gates (exec approval per harness) + trap: `shell-injection`; doctor `check_encoding_discipline` class-checks script hygiene. No kit-owned sandbox: Windows Home has none — declared honestly. |
| ASI06 | Memory and Context Poisoning | OPS §5 treats fetched/subagent content as data; `security-and-hardening` covers memory trust; provenance frontmatter/lint and `memory-poisoning` scenario provide checks. |
| ASI07 | Insecure Inter-Agent Communication   | OPS dispatch discipline: subagent output is DATA to verify, not verdicts to obey (hub `send`/`wait` contract; verification-before-completion skill); fable-judge skill re-verifies claimed results. |
| ASI08 | Cascading Failures                   | trap: `infinite-retry-masking`, `silent-failure`, `dead-flag`; results store (schema-v1, append-only) + evidence trend make failure visible instead of self-reinforcing. |
| ASI09 | Human-Agent Trust Exploitation | `false-done` and `converge-audit` scenarios; OPS §3 requires applicable evidence, honest limitations and reviewer-owned signoff. |
| ASI10 | Rogue Agents                         | trap: `false-done` + task oracle `verify.py` gates (task-smoke 4) + ImpossibleBench canaries (`005-canary-oneoff`, `006-canary-conflicting`: mutated oracles a hack could pass but honest work cannot; a canary PASS is recorded as `hacked` evidence, excluded from pass-rate baselines); results store append-only (no history rewrite); doctor manifest sync detects skill-tree tampering. |

## AST — Agentic Skills Top 10

| ID    | Risk                          | Kit control (wave1) |
|-------|-------------------------------|---------------------|
| AST01 | Malicious Skills              | Skills are first-party (no registry installs). doctor control: integrity manifest hash-pins every `skills/*/SKILL.md` (Task 2); AST01 cryptographic signing explicitly deferred (roadmap "Deferred": no key infrastructure for one user). |
| AST02 | Supply Chain Compromise       | doctor `check_skill_supply_chain` — WARN on inconsistent optional `license:` frontmatter across skills (hygiene seed; ok=True, soft-gate semantics). First-party-only distribution is the primary control. |
| AST03 | Over-Privileged Skills        | harness-owned, N/A — skills carry no permission manifests; every side-effecting call flows through harness permission gates. Kit keeps skills instruction-only (no bundled executables). |
| AST04 | Insecure Metadata | doctor validates owned-skill frontmatter; `profile.yml` declares 37 owned skills, with foreign directories excluded. |
| AST05 | Untrusted External Instructions | OPS §5 and `security-and-hardening` separate retrieved data from instructions; `compaction-continuity` checks preservation of the user's corrections. |
| AST06 | Weak Isolation | Sandbox/approval enforcement belongs to the host. OPS §1 defines authority but cannot enforce filesystem or network isolation. |
| AST07 | Update Drift                  | integrity manifest (Task 2): `--update`-regenerated SHA-256 pins; doctor `check_integrity` FAILs on any drifted/added/removed control-plane file; deploy refuses to copy drifted trees (exit 3). |
| AST08 | Poor Scanning                 | N/A by design, stated plainly: the corpus is first-party, small, and reviewed at commit time; external scanners target registry-scale distribution the kit does not have (YAGNI). Revisit if skills are ever accepted from outside. |
| AST09 | No Governance                 | profile.yml manifest = the skill inventory; doctor manifest sync = drift alarm; usage_audit measures which skills actually fire (retirement discipline: 42→36 re-audit in v3.4.6). |
| AST10 | Cross-Platform Reuse | doctor checks engine-copy consistency; deploy.py generates lightweight OPS pointers and byte-verifies manifest-owned skills. Host activation requires a separate runtime check. |

## Sources

- OWASP Top 10 for Agentic Applications (2025-12-09):
  https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications/
- OWASP Agentic Skills Top 10 (v1.0, 2026-03):
  https://owasp.org/www-project-agentic-skills-top-10/
- Cymulate CBSE series (config-as-boundary threat model behind Task 2):
  https://cymulate.com/blog/the-race-to-ship-ai-tools-left-security-behind-part-1-sandbox-escape/
- ASI06 doctrine (memory-is-attack-surface):
  https://genai.owasp.org/2026/05/13/memory-is-a-feature-it-is-also-an-attack-surface/
