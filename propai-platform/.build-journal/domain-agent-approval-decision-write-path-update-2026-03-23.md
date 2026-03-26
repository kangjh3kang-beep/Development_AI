# Domain-agent approval decision write-path update

Date: 2026-03-23
Stage: 42

## Summary

Completed the missing write-side for the live domain-agent approval queue.

The workspace could already read persisted execution history and pending approvals, but operators still had to leave the product to resolve the queue. This stage adds a first-class approval decision endpoint and binds approve/reject actions into the live agent workspace so queue state and execution history stay synchronized after each decision.

## Implemented

### Backend approval decision contract and endpoint

Files:

- `packages/schemas/models.py`
- `apps/api/services/domain_agents_service.py`
- `apps/api/routers/domain_agents.py`

Changes:

- added `DomainAgentApprovalDecisionRequest`
- extended approval queue item responses with `decided_at`
- added `DomainAgentsService.decide_approval()`
- added `POST /api/v1/agents/domain/approvals/{approval_id}/decision`
- kept tenant scoping and returned `404` for missing approvals

### Frontend approval actions in the live workspace

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`

Changes:

- added approve and reject actions for pending approval queue items
- disabled action buttons while a decision request is in flight
- surfaced write-side failures in the workspace instead of silently dropping them
- invalidated both history and approval queue queries after successful decisions
- synchronized focused and portfolio execution result cards with the updated approval status immediately

### Regression coverage

Files:

- `tests/unit/test_part_f_live_modules.py`
- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`

Coverage:

- approval decision request schema and router registration
- live agent workspace approve flow against the persisted approval queue
- post-decision queue refresh and execution history refresh
- preservation of the existing focused and orchestration execution flows

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx'`
  - `5 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q tests/unit/test_part_f_live_modules.py'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `76 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Add approval rationale input if operators need explicit decision notes instead of the current default workspace message.
2. Add bulk approval actions for portfolio-level queues when multiple pending items belong to the same project.
3. Add approval audit filters and tenant-wide review views if the queue becomes an operational console rather than only a project-scoped workflow.
