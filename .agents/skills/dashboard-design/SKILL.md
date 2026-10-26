---
name: dashboard-design
description: 'Use when designing, redesigning or reviewing marketplace, seller, operations, finance, logistics or analytics dashboards: information hierarchy, KPI and metric semantics, filters, chart and table choice, honest data visualization, dense layouts, and verifying dashboard states in the running app. Not for product UI, themes, tokens or landing pages (design-system), nor posters or static illustrations.'
license: MIT
metadata:
  version: "6.0.0"
---

# Dashboard Design

A dashboard is a decision tool, not a collection of cards. Make data easier to
decide from, and verify the states that matter in the running app before
calling it done.

## Use when

- Redesigning a marketplace, seller or back-office dashboard
- Reworking KPI cards, charts, filters, tables, navigation or detail panels
- Choosing a chart or table form for KPIs, trends, rankings or funnels
- Verifying a changed dashboard in the running app before calling it done

## Workflow

1. **Inspect before proposing.** Read the existing routes, components, tokens,
   data shape and current UI. For every metric find its source definition, unit,
   aggregation, scope, time zone, freshness and comparison period. Never infer
   business meaning from a label or fabricate sample values.
2. **Name the primary decision.** State who uses the dashboard, what they must
   decide, and the three to five questions the screen answers. If a visual
   supports no decision or comparison, a clear value, status or table beats a
   chart. Remove what serves none of those questions.
3. **Set information hierarchy.** Primary status and action first, then KPI
   context, trend or comparison, details, secondary actions. Keep filters and
   the active period visible. Use a table when exact values or row-level actions
   matter.
4. **Choose the least complex visual form.** Value for a current KPI, delta for
   comparison, line for a time series, bars for category comparison or ranking,
   table for exact values or row actions, funnel only when stages and
   denominators are defined. Maps, pies, gauges and dual axes only when the data
   genuinely requires them. Keep title, units, time range, scope, comparison
   basis and freshness attached; never hide an essential value behind hover.
5. **Use honest scales and accessible encoding.** Zero baseline for bars unless a
   documented exception is clearer; no distorted axes, unexplained smoothing,
   false precision or truncated labels. Never carry an important difference in
   color alone — add labels, patterns or direct annotations, and give a
   text or table alternative for meaningful charts.
6. **Reuse the project's visual system.** Color meaning stays stable and the
   existing chart library and theme are the default; a new visualization
   dependency needs the case production-first-decisions asks for. Token
   decisions, component states, responsive breakpoints and accessibility
   baseline are design-system's; this skill supplies the dashboard-specific
   questions (metric semantics, density, data states) to answer with it.
7. **Design the data states.** Cover loading, no data, insufficient data, error,
   stale or partial data, permission-limited or disabled actions, long labels
   and numbers, and values outside the expected range. Each explains the next
   useful action and keeps the layout stable. Component-level state styling is
   design-system's.
8. **Reprioritize for small screens.** Stack or reorder content before shrinking
   it; check the primary status and action still come first, long category names
   and large numbers still fit. Horizontal scrolling is acceptable for genuinely
   wide data tables, never for the whole page.
9. **Critique before implementing.** Remove decoration, redundant labels, cards,
   charts or animation where they do not improve comprehension or actionability.
   No removal quota on an interface that is already clear.
10. **Verify in the running app, proportional to the change.** Launch the real
    app (project run instructions; browser/DevTools or Playwright — never a
    source-only inspection). On dynamic pages wait for observable readiness, not
    network silence or fixed sleeps: a bounded condition wait on the route or
    data marker, on the target role/content being visible, or on the loading
    indicator disappearing, then assert the expected content before reading the
    DOM, and watch the console and network panel for failed requests. Sample by
    blast radius: a changed card gets that card's states at the widths it
    appears in; a changed filter, period control or navigation affects every
    view it feeds, so check each distinct view it feeds rather than every tab in
    the product. Exercise the states from step 7 that the change can reach.
    Record surface, viewport, path/state, observed result and pass|defect, fix
    confirmed issues and rerun the affected check.

## Dashboard defaults

- Three to six primary KPIs, and only when each supports a real decision.
- Keep number formats, units, decimal precision and positive/negative
  conventions consistent; make a negative value's meaning explicit.
- Status meaning explicit through text and icon, not color alone.
- Sentence-case labels and action verbs: `Export`, `Filter`, `View details`,
  `Resolve`.
- No gradients, glass effects, excessive pills, emoji icons or uniform rounded
  cards as decoration.
- Do not turn every metric into a chart; a number, comparison or table may be
  the better answer.
- One clear comparison over many competing series; direct labels when the series
  count is small; raw values available when decisions depend on exact amounts.
- Preserve existing product patterns unless there is a documented reason to
  change them.

## Output before coding

Write a short decision list: primary user and decision; retained, moved and
removed content; hierarchy and chosen visual forms with the question each
answers; token or component changes (or "none, reuse existing"); data states and
narrow-width behavior; one risk to check in the running UI. Then implement only
that plan. A new or ambiguous flow goes through brainstorming first.

## Review checklist

- [ ] each visual answers a named question, with numerator, denominator, unit,
      period and scope clear where present
- [ ] primary status and next action are visible without hunting
- [ ] active filters, date range, units, comparison period and data freshness
      are visible whenever such controls exist
- [ ] every meaningful chart has labels plus a non-color-only reading, and its
      text or table fallback preserves the meaning
- [ ] values are comparable without guessing the scale; the view survives
      grayscale, zoom and keyboard navigation
- [ ] narrow width keeps the hierarchy and does not overflow the page
- [ ] error and empty states offer a concrete next action
- [ ] the screen is calmer and clearer than before, not merely decorated

## References

- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Chrome accessibility tooling:
  https://developer.chrome.com/docs/devtools/accessibility/reference