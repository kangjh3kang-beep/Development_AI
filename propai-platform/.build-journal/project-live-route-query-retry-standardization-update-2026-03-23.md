# Project live route query retry standardization update

Date: 2026-03-23
Stage: 38

## Summary

Standardized read-side error handling across the remaining project route live workspaces.

`finance`, `report`, `drone`, `design`, `bim`, and `blockchain` now expose retryable project-metadata query errors through the same card-based UX used in the dashboard workspaces, and `blockchain` now also surfaces retryable failure state for the live `next escrow id` lookup.

## Implemented

### Project route error handling

Files:

- `apps/web/components/projects/ProjectFinanceWorkspaceClient.tsx`
- `apps/web/components/projects/ProjectReportWorkspaceClient.tsx`
- `apps/web/components/projects/ProjectDroneWorkspaceClient.tsx`
- `apps/web/components/projects/ProjectDesignWorkspaceClient.tsx`
- `apps/web/components/projects/ProjectBimWorkspaceClient.tsx`
- `apps/web/components/projects/ProjectBlockchainWorkspaceClient.tsx`

Changes:

- replaced passive project metadata error banners with retryable query error cards
- standardized project route failure messaging around live metadata recovery
- kept route-bound forms usable after retry without changing the existing happy-path flow
- added explicit retryable handling for blockchain `GET /blockchain/escrow/next-id`

### Regression coverage

Files:

- `apps/web/components/projects/__tests__/ProjectFinanceWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectReportWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectDroneWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectDesignWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectBimWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectBlockchainWorkspaceClient.test.tsx`

Coverage:

- retryable project metadata query handling for all six project route workspaces
- retryable `next escrow id` query handling for blockchain live route
- verification that the routed project context recovers correctly after refetch

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `69 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped, 1 warning`

## Next order

1. Apply the same retryable read-side contract to any non-project live client that still exposes plain text error banners without refetch controls.
2. Replace sample-only `kdx` and `feasibility` pages with real backend bindings once supporting read endpoints exist.
3. Expose persisted domain-agent history and approval queue views when read/list APIs are available.
