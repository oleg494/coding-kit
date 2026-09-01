#!/usr/bin/env python3
"""migrate_evals.py — one-off per-skill evals.json migration (wave3 Task 9).

Splits eval/trigger_queries.json into skills/<slug>/evals/evals.json
({skill_name, evals: [{id, prompt, should_trigger}]}), keeping ids stable
(<slug>-<position within the skill's central block>) so baselines pair.
The central file REMAINS as the loader's fallback source — not deleted.
Run once: python eval/migrate_evals.py
"""
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
CENTRAL = KIT / "eval" / "trigger_queries.json"


def main() -> int:
    central = json.loads(CENTRAL.read_text(encoding="utf-8"))
    by_skill: dict[str, list[dict]] = {}
    for q in central:
        by_skill.setdefault(q["skill"], []).append(q)
    total = 0
    for slug, qs in sorted(by_skill.items()):
        d = KIT / "skills" / slug / "evals"
        d.mkdir(parents=True, exist_ok=True)
        payload = {"skill_name": slug,
                   "evals": [{"id": f"{slug}-{i}", "prompt": q["query"],
                              "should_trigger": q["should"]}
                             for i, q in enumerate(qs)]}
        (d / "evals.json").write_text(
            json.dumps(payload, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        total += len(qs)
    print(f"migrated {total} queries into {len(by_skill)} "
          "per-skill evals/evals.json files (central file kept as fallback)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
