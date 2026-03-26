# Domain-agent tenant-wide audit filters update

Date: 2026-03-23
Stage: 45

## Summary

Extended the live domain-agent approval audit from a single-project queue into a tenant-aware operations review surface.

Operators could already review pending approvals for the active project, resolve individual items, and execute project-level bulk decisions. This stage adds tenant-wide read filters, resolved-state inspection, and cross-project metadata so approval operations can review the full queue and recent decisions across the portfolio without leaving the live workspace.

## Implemented

### Backend approval-status normalization for tenant-wide reads

Files:

- `apps/api/routers/domain_agents.py`

Changes:

- normalized `status=all` to the unfiltered branch in `GET /api/v1/agents/domain/approvals`
- preserved existing `pending` behavior for project-scoped queue reads
- enabled the frontend to switch between pending-only and full resolved-state portfolio views without a new endpoint

### Frontend tenant-wide audit filters and cross-project queue view

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`

Changes:

- added audit scope controls to switch between active-project and tenant-wide read models
- added approval-status filters for `pending`, `approved`, `rejected`, and `all`
- added adjustable record-limit controls for history and approval queue reads
- rendered project identifiers inside history and approval cards so cross-project items remain attributable
- rendered decision timestamps for resolved approval items
- constrained bulk approval and rejection controls to project scope only, preventing cross-project batch writes from the tenant-wide view

### Regression coverage

Files:

- `tests/unit/test_part_f_live_modules.py`
- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`

Coverage:

- router-source assertion for the `status in {None, "all"}` normalization branch
- tenant-wide history query path and all-status approval query path
- rendering of cross-project approval metadata in the live workspace
- rendering of resolved approval timestamps
- preservation of project-scoped queue behavior and project-only bulk actions

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q tests/unit/test_part_f_live_modules.py'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx'`
  - `8 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `79 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Add resolved approval rationale presentation polish so approved and rejected items expose the operator note more clearly in tenant-wide review.
2. Add approver-role or policy filters if different reviewer groups should operate on separate approval segments.
3. Split the tenant-wide audit into a dedicated cross-project operations page if queue density grows beyond the embedded live workspace.
