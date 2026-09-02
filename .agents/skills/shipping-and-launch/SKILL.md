---
name: shipping-and-launch
description: Prepares production launches. Use when preparing to deploy to production. Use when you need a pre-launch checklist, when setting up monitoring, when planning a staged rollout, or when you need a rollback strategy.
metadata:
  version: "4.1.0"
---

# Shipping and Launch

## Overview

Ship with confidence. Every launch should be reversible, observable, and incremental.

## When to Use

- Deploying a feature to production for the first time
- Releasing a significant change to users
- Migrating data or infrastructure
- Opening a beta or early access program

## The Pre-Launch Checklist

### Code Quality
- [ ] All tests pass (unit, integration, e2e)
- [ ] Build succeeds with no warnings
- [ ] Lint and type checking pass
- [ ] Code reviewed and approved
- [ ] No `console.log` debugging statements in production code
- [ ] Error handling covers expected failure modes

### Security
- [ ] No secrets in code or version control
- [ ] Dependency audit shows no critical or high vulnerabilities
- [ ] Input validation on all user-facing endpoints
- [ ] Authentication and authorization checks in place
- [ ] Security headers configured (CSP, HSTS, etc.)
- [ ] Rate limiting on authentication endpoints

### Performance
- [ ] Core Web Vitals within "Good" thresholds
- [ ] No N+1 queries in critical paths
- [ ] Images optimized
- [ ] Bundle size within budget
- [ ] Database queries have appropriate indexes

### Infrastructure
- [ ] Environment variables set in production
- [ ] Database migrations applied
- [ ] DNS and SSL configured
- [ ] Health check endpoint exists and responds
- [ ] Logging and error reporting configured

## Feature Flag Strategy

Ship behind feature flags to decouple deployment from release:

```
1. DEPLOY with flag OFF     → Code in production but inactive
2. ENABLE for team/beta     → Internal testing in production
3. GRADUAL ROLLOUT          → 5% → 25% → 50% → 100%
4. MONITOR at each stage    → Watch error rates, latency, feedback
5. CLEAN UP                 → Remove flag within 2 weeks of full rollout
```

Rules:
- Every feature flag has an owner and expiration date
- Clean up flags within 2 weeks of full rollout
- Don't nest feature flags
- Test both flag states in CI

## Staged Rollout

```
1. DEPLOY to staging → full test suite + manual smoke test
2. DEPLOY to production (flag OFF) → verify health check, error monitoring
3. ENABLE for team (24h monitoring window)
4. CANARY rollout (5% of users) → 24-48h monitoring
5. GRADUAL increase (25% → 50% → 100%)
6. FULL rollout → monitor 1 week → clean up flag
```

### Rollout Decision Thresholds

| Metric | Advance (green) | Hold (yellow) | Roll back (red) |
|--------|-----------------|---------------|-----------------|
| Error rate | Within 10% of baseline | 10-100% above | >2x baseline |
| P95 latency | Within 20% of baseline | 20-50% above | >50% above |
| Client JS errors | No new error types | <0.1% of sessions | >0.1% of sessions |

## Rollback Strategy

Every deployment needs a rollback plan:
- **Trigger:** Error rate > 2x baseline, P95 latency spike, user-reported issues, data integrity issues
- **Steps:** Disable feature flag OR deploy previous version → verify → communicate
- **Time to rollback:** Feature flag < 1 min, Redeploy < 5 min, DB rollback < 15 min

## Post-Launch Verification (first hour)

1. Check health endpoint returns 200
2. Check error monitoring dashboard (no new error types)
3. Check latency dashboard (no regression)
4. Test the critical user flow manually
5. Verify logs are flowing
6. Confirm rollback mechanism works (dry run)

## Red Flags
- Deploying without a rollback plan
- No monitoring or error reporting in production
- Big-bang releases (everything at once)
- Feature flags with no expiration or owner
- "It's Friday afternoon, let's ship it"