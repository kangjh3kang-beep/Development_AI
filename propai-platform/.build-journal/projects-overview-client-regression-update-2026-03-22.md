# Projects overview client regression update

Date: 2026-03-22
Stage: 31

## Summary

Finished the next execution slice by adding focused client-level regression coverage for the shared `ProjectsOverviewClient` that powers the dashboard project-list experience.

This moves the frontend test surface one step deeper than route-shell smoke coverage. The projects list page is now covered at both the page-shell layer and the client interaction layer.

## Implemented

### Projects overview client tests

Files:

- `apps/web/components/projects/__tests__/ProjectsOverviewClient.test.tsx`

Coverage:

- loading skeleton state while the project list query is pending
- live project card rendering from the `/projects` response
- grid to list mode switching through the shared app store
- project selection through the shared project store
- detail route link wiring for the selected project

### Test stability adjustments

The new tests explicitly reset shared Zustand stores and keep those resets inside `act(...)` boundaries so the suite stays free of React act warnings while covering external store updates.

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `45 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend coverage now includes:

- dashboard route shells
- operations live pages
- project detail subroutes
- CAD/map/realtime utility regressions
- projects overview client behavior

The next meaningful gap is no longer the projects list itself. It is broader dashboard navigation or higher-level integration flow coverage.

## Next order

1. Add integration-level tests for the dashboard home entry cards and navigation links so route-to-route entry flow is exercised end-to-end.
2. Consider adding empty-state and error-state UI to `ProjectsOverviewClient`, then cover those branches explicitly.
3. Revisit the mock-only `agent` route if the goal is to replace preview mode with a live orchestration surface.
