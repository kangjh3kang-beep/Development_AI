# Agent live orchestration workspace update

Date: 2026-03-22
Stage: 35

## Summary

Promoted the remaining mock-only `agent` dashboard route into a live domain-agent orchestration workspace.

The route now binds to the existing `/api/v1/agents/domain/run` and `/api/v1/agents/domain/multi-analysis` APIs, supports live project selection, focused execution, multi-domain orchestration, and surfaces approval-gated outcomes directly in the dashboard.

The same pass also restored the frontend verification gates after unrelated regressions reappeared in `ThreeScene`, `KDX`, and `feasibility` screens.

## Implemented

### Agent route promotion

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/agent/page.tsx`
- `apps/web/app/[locale]/(dashboard)/layout.tsx`
- `apps/web/public/locales/en/common.json`
- `apps/web/public/locales/ko/common.json`
- `apps/web/public/locales/zh-CN/common.json`

Changes:

- replaced the mock `AgentTimeline` route wiring with a live orchestration workspace
- added live project selection and manual UUID targeting
- added focused single-domain execution via `/agents/domain/run`
- added multi-domain orchestration via `/agents/domain/multi-analysis`
- rendered confidence, recommendation, approval state, and domain summary cards
- moved `agent` from sidebar preview-only status into the main dashboard navigation
- updated the route-level page copy from preview language to live orchestration language

### Regression coverage

Files:

- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`

Coverage:

- live focused run contract
- live multi-domain orchestration contract
- project-store propagation for the selected live project
- auth-required error handling when runtime access is unavailable
- dashboard route shell coverage updated from preview mode to live workspace mode

### Frontend gate restoration

Files:

- `apps/web/components/cad/ThreeScene.tsx`
- `apps/web/components/dashboard/kdx/KdxRealtimeChart.tsx`
- `apps/web/app/dashboard/kdx/page.tsx`
- `apps/web/app/feasibility/page.tsx`

Changes:

- restored the lightweight canvas-based CAD preview expected by the current regression suite
- removed the broken `three` dependency path from the dashboard test surface
- fixed KDX chart typing and replaced impure sample log rendering with deterministic sample data
- rewrote the feasibility sample page with typed report data and lint-clean chart wiring

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `54 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped, 1 warning`

## Next order

1. Add explicit error-state UI and regression coverage to other live workspaces that still assume successful API responses.
2. Add route-level smoke coverage for auxiliary dashboard pages like `kdx` and `feasibility` if they remain part of the active operator path.
3. Expose persisted domain-agent history and approval queue views once the backend gains list/read endpoints for `domain_agents`.
