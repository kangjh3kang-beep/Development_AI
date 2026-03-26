# KDX and feasibility live binding update

Date: 2026-03-23
Stage: 40

## Summary

Replaced the remaining sample-only auxiliary routes with real backend bindings.

`kdx` now reads a live monitoring overview from the API and uses the correct websocket origin for stream updates, while `feasibility` now runs persisted financial analysis scenarios through `financial_analyses` and renders the latest saved snapshot in the frontend workspace.

## Implemented

### Backend contracts and services

Files:

- `packages/schemas/models.py`
- `apps/api/services/kdx_integration_service.py`
- `apps/api/services/feasibility_service.py`
- `apps/api/routers/kdx.py`
- `apps/api/routers/finance.py`
- `apps/api/auth/rbac.py`

Changes:

- added `KDXOverviewResponse` read contract for monitoring cards and log feed consumption
- added `FeasibilityAnalysisRequest` and `FeasibilityAnalysisResponse` contracts for persisted scenario analysis
- added `KDXIntegrationService.overview()` to aggregate latest metric snapshot, recent telemetry logs, connection status, throughput, and latency
- fixed the KDX router prefix so the actual websocket route matches `/api/v1/kdx/stream`
- added `GET /api/v1/kdx/overview`
- added `POST /api/v1/finance/feasibility`
- added `GET /api/v1/finance/feasibility/{project_id}/latest`
- added `kdx` RBAC policies for read/write access

### Frontend live workspaces

Files:

- `apps/web/components/dashboard/kdx/KdxMonitoringWorkspaceClient.tsx`
- `apps/web/components/dashboard/kdx/KdxRealtimeChart.tsx`
- `apps/web/components/feasibility/FeasibilityWorkspaceClient.tsx`
- `apps/web/app/dashboard/kdx/page.tsx`
- `apps/web/app/feasibility/page.tsx`

Changes:

- replaced the KDX sample dashboard with a live monitoring workspace backed by `/kdx/overview`
- kept the realtime chart on websocket streaming, but now derive the websocket origin from runtime API config instead of hardcoding `localhost`
- replaced the feasibility preview page with a live scenario workspace backed by `/projects` and `/finance/feasibility`
- persisted newly submitted feasibility analyses into the React Query cache to avoid stale refetch overwrites
- added retryable error handling for KDX overview and feasibility project/snapshot reads

### Regression coverage

Files:

- `tests/unit/test_kdx_feasibility_live_modules.py`
- `apps/web/components/dashboard/kdx/__tests__/KdxMonitoringWorkspaceClient.test.tsx`
- `apps/web/components/feasibility/__tests__/FeasibilityWorkspaceClient.test.tsx`
- `apps/web/app/__tests__/auxiliary-route-shells.test.tsx`

Coverage:

- KDX router/source registration and websocket-origin contract
- feasibility request/response schema fields and helper calculations
- KDX connection status/throughput helper behavior
- feasibility cashflow, IRR, and payback helper behavior
- KDX workspace happy path and retry recovery
- feasibility workspace latest-snapshot rendering, live submission, and project-picker retry recovery
- route shell wiring for both auxiliary pages

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/dashboard/kdx/__tests__/KdxMonitoringWorkspaceClient.test.tsx components/feasibility/__tests__/FeasibilityWorkspaceClient.test.tsx app/__tests__/auxiliary-route-shells.test.tsx'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q tests/unit/test_kdx_feasibility_live_modules.py'`
  - `10 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `74 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Expose read/list endpoints for persisted domain-agent executions and approval queues, then bind them to the `agent` live workspace.
2. Add KDX historical metric read endpoints if the realtime chart should preload persisted series instead of starting empty before websocket ticks arrive.
3. Add saved feasibility scenario listing and compare-mode UI once multi-scenario review becomes a user-facing requirement.
