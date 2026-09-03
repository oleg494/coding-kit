---
name: observability-and-instrumentation
description: Instruments code so production behavior is visible and diagnosable. Use when adding logging, metrics, tracing, or alerting. Use when shipping any feature that runs in production and you need evidence it works. Use when production issues are reported but you can't tell what happened from the available data.
license: MIT
metadata:
  version: "4.1.0"
---

# Observability and Instrumentation

## Overview

Code you can't observe is code you can't operate. Instrumentation is not a post-launch add-on — it's written alongside the feature, the same way tests are.

## When to Use

- Building any feature that will run in production
- Adding a new service, endpoint, background job, or external integration
- A production incident took too long to diagnose
- Setting up or reviewing alerting rules

## Process

### 1. Define "working" before instrumenting

Write down 2–4 questions an on-call engineer will ask about this feature:

```
FEATURE: checkout payment retry
QUESTIONS ON-CALL WILL ASK:
1. What fraction of payments succeed on first attempt vs after retry?
2. When a payment fails permanently, why?
3. Is the payment provider slower than usual?
→ Every signal below must help answer one of these.
```

### 2. Pick the right signal

| Signal | Answers | Cost |
|---|---|---|
| **Structured log** | "What happened in this specific case?" | Per-event |
| **Metric** | "How often / how fast, in aggregate?" | Fixed per series |
| **Trace** | "Where did time go across services?" | Per-request, sampled |

Rule: metrics tell you **that** something is wrong, traces tell you **where**, logs tell you **why**.

### 3. Structured logging

Log events, not prose. Every log line is a JSON object with a stable event name:

```typescript
// BAD: logger.info(`Payment ${id} failed for user ${userId}`);
// GOOD:
logger.warn({
  event: 'payment_failed',
  paymentId: id,
  provider: 'stripe',
  errorCode: err.code,
  attempt: n,
}, 'payment failed');
```

**Log levels:**
| Level | Meaning | On-call action |
|---|---|---|
| `error` | Invariant broken | Investigate |
| `warn` | Degraded but handled | Watch for trends |
| `info` | Significant business event | None |
| `debug` | Diagnostic detail | Off in production |

**Correlation IDs are mandatory.** Generate/accept a request ID at the system boundary and attach it to every log line, span, and outbound call.

**Never log secrets, tokens, passwords, or full PII.**

### 4. Metrics

Instrument **RED** on every endpoint: **R**ate, **E**rrors, **D**uration (histogram, not average).

**Cardinality is the failure mode.** Labels must come from small, fixed sets (route template, status class). Never use user IDs, raw URLs, or error messages as labels.

Track averages never, percentiles always. Use histograms: p50/p95/p99.

### 5. Distributed tracing

Use OpenTelemetry — vendor-neutral standard. Auto-instrumentation covers HTTP, gRPC, DB clients with near-zero code.

### 6. Alerting

Alert on **symptoms users feel**, not on causes:
- SYMPTOM (page-worthy): error rate > 1% for 5 min, p99 latency > 2s
- CAUSE (dashboard, not a page): CPU at 85%, one pod restarted

Rules for every alert:
1. It must be actionable
2. It links to a runbook
3. It has a threshold justified by SLO or historical data
4. Two severities only: **page** (act now) and **ticket** (act this week)

### 7. Verify the telemetry itself

Before calling done:
- Force an error in staging → find it in logs by requestId
- Send test traffic → confirm metric series appear
- Follow one request across services in tracing UI
- Fire each new alert once (lower threshold temporarily)

## Verification
- [ ] On-call questions written down, each signal maps to one
- [ ] All log output structured (JSON), correlation ID on every line
- [ ] No secrets in any log line
- [ ] RED metrics for every new endpoint, bounded label sets
- [ ] Latency is a histogram; p95/p99 queryable
- [ ] Every new alert is symptom-based, has a runbook link, was test-fired