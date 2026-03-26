# Live tax, inspection, and auction query hardening update

Date: 2026-03-23
Stage: 37

## Summary

Closed the remaining live read-side gaps in the dashboard workspaces that still assumed successful query responses.

`tax`, `inspection`, and `auction` now surface explicit retryable query-error states instead of silently falling through to empty UI, and `auction` now has direct component-level regression coverage for both its happy-path orchestration and read-side failures.

## Implemented

### Query error handling

Files:

- `apps/web/components/analytics/TaxOperationsWorkspaceClient.tsx`
- `apps/web/components/analytics/InspectionOperationsWorkspaceClient.tsx`
- `apps/web/components/auction/AuctionWorkspaceClient.tsx`

Changes:

- added retryable project picker error cards to the tax live workspace
- added retryable project picker error cards to the inspection live workspace
- added retryable read-side error cards to the auction workspace for:
  - stored auction opportunities
  - active contractor network
  - chatbot session history
- aligned empty-state branches so they do not mask real query failures
- localized auction auth failure messaging through the same live workspace error surface

### Regression coverage

Files:

- `apps/web/components/analytics/__tests__/TaxOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/InspectionOperationsWorkspaceClient.test.tsx`
- `apps/web/components/auction/__tests__/AuctionWorkspaceClient.test.tsx`

Coverage:

- tax project query error rendering and retry behavior
- inspection project query error rendering and retry behavior
- auction workspace happy-path rendering and analysis submission
- auction read-side query error rendering and retry behavior across all three feeds

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `63 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped, 1 warning`

## Next order

1. Apply the same explicit query-error contract to any remaining project-level live clients that still rely on implicit success paths.
2. Replace sample-only `kdx` and `feasibility` pages with live backend bindings when the supporting read endpoints exist.
3. Expose persisted domain-agent history and approval queue views once read/list APIs are available.
