# Dashboard client panel integration update

Date: 2026-03-22
Stage: 34

## Summary

Finished the next execution slice by adding focused integration tests for `DashboardClientPanel`, covering the two real workspace modes and the fallback failure path.

This closes the main remaining gap in the dashboard landing surface. The home panel is now covered not only for navigation, but also for its data-mode branching and store side effects.

## Implemented

### Dashboard client panel tests

Files:

- `apps/web/components/dashboard/__tests__/DashboardClientPanel.test.tsx`

Coverage:

- mock mode summary rendering from `/dashboard/overview`
- mock integration status rendering from `/integration/status`
- featured project propagation into `useProjectStore`
- integration status propagation into `useAppStore`
- live mode summary rendering from `/dashboard/stats`
- live integration status rendering from `/system/version` and `/system/health/full`
- fallback UI for dashboard summary failure
- fallback UI for integration status failure

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `52 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend coverage now includes:

- dashboard home navigation
- dashboard client panel data branching
- dashboard route shells
- operations live pages
- project detail subroutes
- projects overview client behavior
- CAD/map/realtime utility regressions

The next meaningful gaps are no longer the top-level dashboard entry surfaces. The remaining work should focus on deeper live-module behavior or upgrading preview-only routes to real workflows.

## Next order

1. Revisit the mock-only `agent` route if the goal is to promote it from preview mode into a live orchestration workspace.
2. Add explicit error-state UI and tests to other live workspaces that still assume successful API responses.
3. If desired, add broader dashboard interaction tests that connect the home entry surfaces to downstream live pages.
