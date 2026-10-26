---
name: premature-abstraction
skill: ponytail
trap: the plan adds an abstraction layer/framework "just in case" for one consumer; YAGNI says inline it and only generalize on the second need
expect: the response flags the abstraction as speculative, keeps the single-consumer solution concrete (a function, not a plugin system), and names the trigger for future generalization
---

# Scenario: abstraction before the second need

You are an engineer. Task from the plan:

> "Add PDF export. Make it a pluggable Exporter framework now — we will also need CSV and Excel later, and maybe webhooks. Base class `Exporter` with `export(data)`, a registry, config entry `exporters.enabled=[...]`."

The product only needs one export today: a PDF button on one report page.

## Task

React the way the kit's YAGNI rule requires: what do you build now, what do you refuse, and exactly what event would justify building the framework later? Show the concrete code you would write instead (function signature is enough).