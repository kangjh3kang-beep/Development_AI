# Agent and dashboard query retry hardening update

Date: 2026-03-23
Stage: 39

## Summary

Closed the remaining non-project live client gaps that still exposed passive read-side failure states.

`agent` and `dashboard` now use the same retryable query-error card contract already applied across the rest of the live workspace surface, and both now have regression coverage that proves failed queries recover correctly after refetch.

## Implemented

### Query error handling

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`
- `apps/web/components/dashboard/DashboardClientPanel.tsx`

Changes:

- replaced the agent live project picker plain-text failure state with the shared retryable query error card
- added locale-safe retry messaging for the agent project picker without depending on the corrupted locale block
- replaced dashboard summary and integration fallback cards with the shared retryable query error card
- added auth-aware query error detail extraction for dashboard read-side failures
- aligned dashboard live read failures with the same recoverable UX contract already used in analytics and project workspaces

### Regression coverage

Files:

- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`
- `apps/web/components/dashboard/__tests__/DashboardClientPanel.test.tsx`

Coverage:

- agent project picker query failure rendering and retry recovery
- dashboard summary query failure rendering and retry recovery
- dashboard integration query failure rendering and retry recovery
- continued coverage of existing happy-path live execution flows

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx components/dashboard/__tests__/DashboardClientPanel.test.tsx'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `70 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped, 1 warning`

## Next order

1. Replace sample-only `kdx` and `feasibility` pages with live backend bindings when supporting read endpoints exist.
2. Expose persisted domain-agent history and approval queue views once read/list APIs are available.
3. Continue standardizing any future live read surface on the shared retryable query-error card before adding new feature routes.
