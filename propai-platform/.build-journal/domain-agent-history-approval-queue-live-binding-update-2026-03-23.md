# Domain-agent history and approval queue live binding update

Date: 2026-03-23
Stage: 41

## Summary

Completed the missing read-side for the live domain-agent workspace.

Persisted domain-agent executions and approvals were already being stored in the Phase F tables, but the API had no read endpoints and the frontend could not inspect the saved queue. This stage adds those read contracts end to end and binds them into the existing agent orchestration workspace with retryable query handling.

## Implemented

### Backend read-side contracts and endpoints

Files:

- `packages/schemas/models.py`
- `apps/api/services/domain_agents_service.py`
- `apps/api/routers/domain_agents.py`

Changes:

- added `DomainAgentHistoryResponse` and `DomainAgentApprovalQueueResponse` contracts
- added persisted history item and approval queue item response models
- added `DomainAgentsService.list_history()`
- added `DomainAgentsService.list_approval_queue()`
- added `GET /api/v1/agents/domain/history`
- added `GET /api/v1/agents/domain/approvals`
- kept the existing write-side `/run` and `/multi-analysis` contracts unchanged

### Frontend live workspace binding

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`

Changes:

- added live read queries for persisted domain-agent execution history
- added live read queries for the persisted approval queue
- rendered both read models as dedicated cards beneath the focused and portfolio results
- standardized both read queries on the shared retryable query-error card contract
- invalidated history and approval queue queries immediately after successful focused or multi-domain execution

### Regression coverage

Files:

- `tests/unit/test_part_f_live_modules.py`
- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`

Coverage:

- domain-agent history and approval queue response model fields
- domain-agent history and approval queue router registration
- agent workspace happy path with persisted history and approval queue rendering
- history and approval queue query-error rendering and retry recovery
- preservation of existing focused analysis and orchestration flows

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx'`
  - `4 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q tests/unit/test_part_f_live_modules.py'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `75 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Add approval decision endpoints so pending queue items can be approved or rejected directly from the live agent workspace.
2. Add filtered tenant-wide history views if the workspace needs cross-project operational review rather than only project-scoped inspection.
3. Add SSE/WebSocket orchestration history linkage if the long-running `/api/v1/agents/analyze/ws/{project_id}` stream should persist step-level execution traces into the same read model.
