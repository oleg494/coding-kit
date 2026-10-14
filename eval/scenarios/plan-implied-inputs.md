---
name: plan-implied-inputs
skill: writing-plans
trap: a plan copies implementation bodies while leaving cross-task contracts and implied failure cases undefined
expect: produce a concise plan only; preserve exact constraints, specify consumed and produced interfaces, assign empty and malformed input checks to the parser task and failed-write behavior to the exporter task; do not implement, require a new approval, or invent extra product features
---

# Scenario: lean plan with implied input checks

Plan only: extend an existing Python 3.12 standard-library CLI to read a UTF-8
CSV containing columns sku and quantity, sum quantities per sku, and atomically
replace a JSON output file. No dependencies; malformed rows must report row
numbers and leave existing output intact. A header-only file should export an
empty JSON object. Preserve the current command-line interface.

Two implementation tasks will own parsing and export. The draft says only
"Task A: parse CSV; Task B: write JSON; test one normal file" and includes
three pages of speculative implementation code. Give the replacement plan;
file names are proposals because this is a text-only exercise without repo
access, not observed source locations.
