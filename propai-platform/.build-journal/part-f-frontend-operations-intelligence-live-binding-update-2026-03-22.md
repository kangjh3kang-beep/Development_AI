# Part F frontend operations intelligence live binding update

Date: 2026-03-22
Stage: 21

## Summary

Removed the last dead frontend analytics dependency from `analytics/iot` and replaced it with a live operations intelligence workspace.

The page now binds to real operational APIs instead of the non-existent `/analytics/iot` endpoint.

## Implemented

### Operations intelligence workspace

Files:

- `apps/web/components/analytics/OperationsIntelligenceWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/analytics/iot/page.tsx`

Bound live operations:

- `GET /projects?page=1&page_size=20`
- `POST /maintenance/detect-anomaly`
- `POST /tenant/feedback/analyze`
- `POST /tenant/satisfaction/nps`
- `POST /digital-twin/asset-intelligence`

Key behavior:

- project-aware execution using either live project selection or manual UUID entry
- predictive maintenance anomaly detection with work-order visibility
- tenant feedback sentiment analysis and AI reply generation
- NPS and occupancy/arrears-driven tenant health calculation
- asset intelligence snapshot generation using the latest persisted operational signals

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
- `python -m pytest -q`
  - `817 passed, 31 skipped`

## Result

Frontend pages that previously depended on dead analytics endpoints:

- `analytics/investment`
- `analytics/esg`
- `analytics/iot`

are now all redirected to live operational workspaces.

## Next order

1. Add dedicated navigation and landing surfaces for live `maintenance`, `tenant`, and `asset intelligence` modules if these should exist outside analytics.
2. Introduce frontend smoke or E2E coverage for the new live workspaces.
3. Revisit any remaining placeholder dashboards that still exist only for visual scaffolding.
