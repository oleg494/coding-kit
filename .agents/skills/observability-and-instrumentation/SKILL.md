---
name: observability-and-instrumentation
description: 'Use when adding or repairing logging, metrics, tracing, or alerting so production behavior is visible and diagnosable: a new service or integration, a feature that needs evidence it works, an incident that took too long to diagnose, alerts that page for the wrong thing. Not for release, rollout or rollback decisions (shipping-and-launch).'
license: MIT
metadata:
  version: "6.0.0"
---

# Observability and instrumentation

Instrumentation ships with the feature, like tests.

## Define "working" first

List 2–4 questions on-call will ask — retry-adjusted success rate, why a case failed permanently, is the provider slow now. Every signal answers one; one that answers none is cost.

## Scope per component

Instrument each component's boundary, not every function.

- **Request-serving (HTTP, gRPC, queue):** RED per route template — rate, errors by status class, duration histogram — plus saturation of the pool or queue it competes for, from middleware in one place. A specific question can justify more; a payment path may warrant a span per provider call.
- **Job, worker:** outcome, duration, items, retries, dead-letter count per run. Queue lag beats per-item logs; aggregate per job, no label per item.
- **Library:** nothing unbidden — take a logger and metrics handle from the host, or expose hooks; no private exporter, no stdout.
- **CLI:** exit code plus stderr diagnostic; structured output only for a supervisor.

Logs explain one case, metrics aggregate, traces localize across services — metrics say that, traces where, logs why. Cost is per event, per label set, per sampled request.

## Logging

One structured object per business event, with a stable event name and stable, typed field names a query written today still matches next month; ids and codes rather than prose (`event: payment_failed, provider, errorCode, attempt`).

- Identifiers, not payloads: no bodies, tokens or full personal data even at debug; log an id or hash, pseudonymous where it names a person.
- One event per state change, not per loop iteration; a request or trace id where a path crosses components (service → queue → worker), since inside one process a stack trace suffices.
- Route library logging through your formatter, quiet the noisy ones in config, and redact known secret patterns in the collector: one forgotten call must not leak a token.

## Metrics

Labels come from small fixed sets — never a user id, raw URL, error message or request id; a counter plus a log line answers "which one". Histograms with p50/p95/p99, since an average hides the tail; unit in the name (`http_request_duration_seconds`); counters up only; sample the hot path.

## Tracing

OpenTelemetry, auto-instrumentation for HTTP, gRPC and database clients first. Span names describe the operation (`GET /orders/:id`), attributes only for keys you search by. Propagate context across process and queue boundaries — a trace stopping at the queue means the producer never injected it. Sample at the edge and record the choice.

## Alerting

Alert on symptoms users feel; causes go on a dashboard (CPU at 85%, one restart). Each alert is actionable or becomes a ticket, links its runbook, takes its threshold from an SLO or measured baseline rather than a copied default, is page or ticket only, guards scope (a shared dashboard's baseline is not this service's), and resolves itself without re-paging.

## Verify the telemetry itself

Wrong instrumentation argues with the incident:

- Force an error in staging; find it by request id.
- Send test traffic; confirm your labels appear — a label typo silently creates a new series.
- Follow one request across components in the trace UI.
- Fire each alert once by lowering its threshold, then restore it.
- Emit a synthetic canary secret through the logging path; confirm the collector redacts or rejects it.
