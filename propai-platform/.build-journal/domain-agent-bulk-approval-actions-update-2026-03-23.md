# Domain-agent bulk approval actions update

Date: 2026-03-23
Stage: 44

## Summary

Extended the live domain-agent approval queue with project-level bulk approval and rejection actions.

Operators could already resolve a single pending approval item and attach an optional note, but portfolio review still required repeated per-item writes. This stage adds a batch decision contract in the backend and exposes bulk actions in the live workspace so the full pending queue for the active project can be resolved in one operation.

## Implemented

### Backend batch approval decision contract and endpoint

Files:

- `packages/schemas/models.py`
- `apps/api/services/domain_agents_service.py`
- `apps/api/routers/domain_agents.py`

Changes:

- added `DomainAgentApprovalBatchDecisionRequest`
- added `DomainAgentApprovalBatchDecisionResponse`
- added `DomainAgentsService.decide_approvals_batch()`
- added `POST /api/v1/agents/domain/approvals/decision-batch`
- constrained batch writes to the active tenant, active project, and pending approvals only

### Frontend bulk queue actions

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`

Changes:

- added a bulk approval action panel when more than one pending approval exists for the active project
- added shared batch-note capture for project-level approval and rejection actions
- routed batch actions to the new backend decision-batch endpoint
- synchronized focused and portfolio execution cards with bulk decision statuses immediately
- disabled single-item actions while a bulk decision request is in flight
- cleared resolved per-item notes after successful batch writes

### Regression coverage

Files:

- `tests/unit/test_part_f_live_modules.py`
- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`

Coverage:

- batch approval request and response model fields
- router registration for the new decision-batch endpoint
- live workspace bulk-approve flow with a custom shared note
- queue invalidation and execution-history refresh after batch writes
- preservation of the existing single-item approval and rejection flows

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q tests/unit/test_part_f_live_modules.py'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx'`
  - `7 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `78 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Add tenant-wide approval audit filters and a cross-project queue view for operations review.
2. Add resolved approval history rendering with decision timestamp and rationale so batch decisions remain inspectable after queue depletion.
3. Add role-specific bulk approval policies if different approver roles should be segmented into separate operational queues.
