# Live workspace error states and auxiliary route smoke update

Date: 2026-03-23
Stage: 36

## Summary

Hardened the remaining live analytics workspaces so query failures no longer collapse into silent empty states.

`investment`, `energy`, and `operations` now surface retryable query-specific error cards for live project and dashboard data fetches, and auxiliary `kdx` / `feasibility` pages are now pinned with route-level smoke coverage.

## Implemented

### Shared query error UX

Files:

- `apps/web/components/analytics/WorkspaceQueryErrorCard.tsx`
- `apps/web/components/analytics/InvestmentOperationsWorkspaceClient.tsx`
- `apps/web/components/analytics/EnergyOperationsWorkspaceClient.tsx`
- `apps/web/components/analytics/OperationsIntelligenceWorkspaceClient.tsx`

Changes:

- added a reusable inline query error card with alert styling and retry action
- surfaced explicit live query failures in the investment workspace for:
  - project picker
  - AI cost dashboard
  - regional portal market data
- surfaced explicit live query failures in the energy workspace for the certification project picker
- surfaced explicit live query failures in the operations workspace for the live project picker
- preserved manual UUID targeting even when project queries fail
- prevented the investment AI cost view from falling through to a misleading empty state while the query is actually in error

### Regression coverage

Files:

- `apps/web/components/analytics/__tests__/InvestmentOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/EnergyOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/OperationsIntelligenceWorkspaceClient.test.tsx`
- `apps/web/app/__tests__/auxiliary-route-shells.test.tsx`

Coverage:

- live query error rendering and retry behavior for investment workspace cards
- live query error rendering and retry behavior for energy project loading
- live query error rendering and retry behavior for operations project loading
- KDX monitoring route shell render contract
- feasibility preview route render and timed sample-analysis progression

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `59 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped, 1 warning`

## Next order

1. Add the same explicit query-error treatment to any remaining live workspace that still assumes successful read-side responses.
2. Promote auxiliary `kdx` / `feasibility` pages from sample-only shells once live backend bindings exist.
3. Attach persisted domain-agent history and approval queue screens when read/list endpoints are available.
