# Dashboard home navigation integration update

Date: 2026-03-22
Stage: 32

## Summary

Finished the next execution slice by adding integration-level frontend tests for the root dashboard home entry flow.

This stage goes deeper than route-shell smoke coverage. The new tests render the real dashboard home cards and verify the actual navigation destinations and card copy that operators see on the landing screen.

## Implemented

### Dashboard home navigation tests

Files:

- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`

Coverage:

- hero CTA link to `/projects`
- hero CTA link to `/auction`
- overview card destinations for:
  - `/tax`
  - `/auction`
  - `/maintenance`
- overview card descriptions for the root dashboard landing modules

### Digital twin smoke realignment

Files:

- `apps/web/app/[locale]/(dashboard)/__tests__/operations-live-pages.test.tsx`

Coverage update:

- aligns the digital twin route test with the current page composition
- mocks `DigitalTwinAnomalyDashboard`
- verifies the anomaly dashboard mount point plus the asset-intelligence workspace shell

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `47 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend coverage now includes:

- dashboard home navigation flow
- dashboard route shells
- operations live pages
- project detail subroutes
- projects overview client behavior
- CAD/map/realtime utility regressions

The next meaningful gap is no longer dashboard navigation. The next step should move toward deeper integration behavior or missing UI states.

## Next order

1. Add explicit empty-state and error-state UI to `ProjectsOverviewClient`, then cover those branches in tests.
2. Add higher-level integration tests around dashboard client data panels if operator dashboard health states need stronger regression coverage.
3. Revisit the mock-only `agent` route if the goal is to convert it from preview mode into a live orchestration workspace.
