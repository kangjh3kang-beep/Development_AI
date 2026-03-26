# Projects overview empty and error states update

Date: 2026-03-22
Stage: 33

## Summary

Finished the next execution slice by adding explicit empty-state and error-state UI to the shared `ProjectsOverviewClient`, along with retry behavior and multilingual workspace labels for those branches.

This closes one of the last obvious UX gaps in the project list flow. The client no longer assumes that `/projects` always returns a populated list.

## Implemented

### Projects overview client state handling

Files:

- `apps/web/components/projects/ProjectsOverviewClient.tsx`

Behavior:

- keeps the existing loading skeleton branch
- renders a dedicated empty-state card when the project list is empty
- renders a dedicated error-state card when the project query fails
- surfaces the error detail when available
- provides a retry button that triggers `refetch()`

### Projects overview regression expansion

Files:

- `apps/web/components/projects/__tests__/ProjectsOverviewClient.test.tsx`

Coverage:

- loading skeleton state
- populated live list rendering
- grid/list mode switching
- project selection and detail link wiring
- empty-state UI
- error-state UI plus retry flow

### Multilingual label expansion

Files:

- `apps/web/i18n/get-dictionary.ts`
- `apps/web/public/locales/en/common.json`
- `apps/web/public/locales/ko/common.json`
- `apps/web/public/locales/zh-CN/common.json`

Added labels:

- `emptyStateTitle`
- `emptyStateDescription`
- `errorStateTitle`
- `errorStateDescription`
- `retryLabel`

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `49 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend coverage now includes:

- dashboard home navigation
- dashboard route shells
- operations live pages
- project detail subroutes
- projects overview client behavior, including empty/error branches
- CAD/map/realtime utility regressions

The next meaningful frontend gap is less about missing basic states and more about deeper integration behavior in the live dashboard data panels or converting preview-only surfaces to live workflows.

## Next order

1. Add integration-level tests around `DashboardClientPanel` for live vs mock summary and integration-status states.
2. Revisit the mock-only `agent` route if the goal is to turn it into a live orchestration workspace.
3. If desired, add explicit empty/error UX to other live workspaces that still assume successful API responses.
