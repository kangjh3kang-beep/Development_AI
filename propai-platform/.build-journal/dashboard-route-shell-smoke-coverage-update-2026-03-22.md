# Dashboard route shell smoke coverage update

Date: 2026-03-22
Stage: 30

## Summary

Finished the next execution slice by adding route-level smoke coverage for the remaining thin dashboard wrapper pages that were not yet covered by the frontend test suite.

This stage closes the gap between the already-covered live project-detail routes and the higher-level dashboard shells that mostly compose placeholders, hero copy, and client workspace entrypoints.

## Implemented

### Dashboard shell smoke tests

Files:

- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`

Coverage:

- dashboard home
- projects overview route
- mock agent preview route
- auction route shell
- tax route shell
- inspection route shell
- analytics investment route shell
- analytics ESG/energy route shell
- analytics IoT/operations route shell

### Mock strategy

The new test file keeps the route-shell focus narrow by mocking:

- `ModulePlaceholder`
- `OverviewCard`
- `DashboardClientPanel`
- `ProjectsOverviewClient`
- auction and analytics workspace clients
- `AgentTimeline`
- dictionary, module copy, and mock snapshot loaders

This keeps the tests centered on page wiring, labels, runtime status badges, and workspace mount points rather than duplicating lower-level component tests that already exist elsewhere.

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `42 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Dashboard route-level smoke coverage now includes:

- root dashboard shell
- operations live pages
- analytics wrapper pages
- auction wrapper page
- projects list page
- project detail subroutes
- mock agent preview page

The main remaining work is no longer route-shell coverage. The next meaningful increments are either deeper integration coverage or promoting preview/editor routes into richer live experiences.

## Next order

1. Add focused tests for `ProjectsOverviewClient` so the projects list route has both shell coverage and client-level behavior coverage.
2. Add integration-level tests around the dashboard home cards or navigation flows if route-to-route entry assurance is needed.
3. Revisit the mock-only `agent` route if the goal is to convert it from preview mode into a live orchestration workspace.
