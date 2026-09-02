---
name: dashboard-design
description: 'Use when designing, redesigning, or reviewing marketplace, seller, operations, finance, logistics, or analytics dashboards: information hierarchy, KPIs, filters, charts, tables, honest data visualization, design tokens, responsive behavior, loading/empty/error states, and post-change UI verification in the running app. Not for posters, presentations, or static illustrations.'
metadata:
  version: "4.0.2"
---

# Dashboard Design

Design dashboards as decision tools, not collections of cards. Make data easier to decide from, not merely decorative. A dashboard is not ready until its important states and interaction paths are verified in the browser, not only in source.

## Use when

- Redesigning a marketplace or back-office dashboard
- Reworking KPI cards, charts, filters, tables, navigation, or detail panels
- Choosing chart/table forms for KPIs, trends, rankings, funnels
- Verifying a changed dashboard UI in the running app before calling it done
- Improving visual hierarchy, density, responsive behavior, or empty states

## Do not use when

- The task is only backend, data modeling, or query optimization
- The user asks for a poster, presentation, logo, or static illustration

## Workflow

1. **Inspect before proposing.** Read the existing routes, components, tokens, data shape, and current UI. For every metric find the source definition, unit, aggregation, scope, time zone, freshness, and comparison period — never infer business meaning from a label or fabricate sample values.
2. **Name the primary decision.** State who uses the dashboard, what they need to decide, and the three to five questions the screen must answer. If a visual supports no decision or comparison, prefer a clear value, status, or table over a chart. Remove elements that do not support those questions.
3. **Set information hierarchy.** Put the primary status and action first, then KPI context, trend or comparison, details, and secondary actions. Keep filters and the active period visible. Use a table when exact values or row-level actions matter.
4. **Choose the least complex visual form.** KPI for a current value, delta for comparison, line for time series, bars for category comparison/ranking, table for exact values or row actions, funnel only when stages and denominators are defined. Maps, pies, gauges, and dual axes only when the data genuinely requires them. Keep title, units, time range, scope, comparison basis, and freshness attached — no hover-only essential values.
5. **Use honest scales and accessible encoding.** Zero baseline for bars unless a documented exception is clearer; no distorted axes, unexplained smoothing, false precision, or truncated labels. Never communicate important differences through color alone — add labels, patterns, or direct annotations; provide a text/table alternative for meaningful charts.
6. **Define a compact visual system.** Prefer the existing design tokens. If none exist, define semantic tokens for surface, text, muted text, border, success, warning, danger, accent, spacing, type scale, radius, and elevation. Components must consume tokens instead of scattered raw colors. Keep color meaning stable across the product.
7. **Design every meaningful state.** Cover loading, no data, insufficient data, error, stale/partial data, disabled/permission-limited actions, long labels or numbers, and values outside the expected range. Explain the next useful action and keep the layout stable.
8. **Handle responsive behavior intentionally.** Check desktop, tablet, and mobile layouts. Stack or reprioritize content before shrinking it; recheck long category names and large numbers. Allow horizontal scrolling only for genuinely wide data tables; never let the whole page overflow. Keep keyboard focus visible and respect reduced-motion preferences.
9. **Critique before implementation.** Remove one decorative element, one redundant label, and any card, chart, or animation that does not improve comprehension or actionability.
10. **Verify in the running app.** A rendered check is part of the work, not optional follow-up: launch the real app (project run instructions, browser/DevTools or Playwright — never a source-only inspection), inspect representative viewports (1440/1024/768/375px or closest supported), exercise navigation, period controls, filters, tabs, sorting, pagination, row actions, and dialogs, and check the state matrix from step 7 plus the browser console for errors. Fix confirmed issues and rerun the affected check; claim completion only after the rerun is clean. Record evidence: surface, viewport, path/state, observed result, pass|defect, location.

## Dashboard defaults

- Start with three to six primary KPIs only when each supports a real decision.
- Keep number formats, units, decimal precision, and positive/negative conventions consistent; make negative/positive meaning explicit.
- Make status meaning explicit with text, iconography, and color where appropriate.
- Prefer sentence-case labels and action verbs such as `Export`, `Filter`, `View details`, and `Resolve`.
- Do not use gradients, glass effects, excessive pills, emoji icons, or uniform rounded cards as decoration.
- Do not turn every metric into a chart; a clear number, comparison, or table may be better.
- Prefer one clear comparison over many competing series; use direct labels when the number of series is small; keep raw values available when decisions depend on exact amounts.
- Reuse the existing chart library and theme; do not add a new visualization dependency for one chart.
- Preserve existing product patterns unless there is a documented reason to change them.

## Output before coding

Write a short design decision list:

- primary user and decision;
- retained, moved, and removed content;
- layout hierarchy and chosen visual forms (with the question each answers);
- token or component changes;
- state and responsive behavior;
- one risk to verify in the running UI.

Then implement only that plan. For a new or ambiguous flow, use a separate discovery/brainstorming skill before changing code.

## Review checklist

- What question does this visual answer? Are numerator, denominator, unit, period, and scope clear?
- Can a user identify the primary status and next action without hunting?
- Are active filters, date range, units, comparison period, and data freshness clear?
- Does every important chart have labels and a non-color-only interpretation, and does the text/table fallback preserve the meaning?
- Can users compare values without guessing the scale? Does the visual work in grayscale, zoom, keyboard navigation, and mobile width?
- Does the screen remain usable with keyboard, zoom, reduced motion, and narrow widths? (WCAG 2.2 baseline: landmarks, heading order, accessible names, table headers, focus management, contrast.)
- Are error and empty states actionable rather than vague?
- Is the page calmer and clearer after the redesign, or merely more decorated?

## References

- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Chrome accessibility tooling: https://developer.chrome.com/docs/devtools/accessibility/reference
