# Domain-agent approval rationale UI update

Date: 2026-03-23
Stage: 43

## Summary

Extended the live domain-agent approval queue so operators can provide an explicit decision note before approving or rejecting a pending item.

The backend write endpoint already accepted optional rationale text, but the workspace only sent fixed default messages. This stage adds per-item note input to the approval queue, preserves the existing default rationale fallback, and locks the behavior with a dedicated rejection-path regression.

## Implemented

### Frontend approval note capture

Files:

- `apps/web/components/agent/AgentOrchestrationWorkspaceClient.tsx`

Changes:

- added per-approval local note state keyed by `approval_id`
- added an optional decision note textarea for every pending queue item
- routed typed note content into the existing approval decision write endpoint
- preserved the previous default rationale messages when the note is left blank
- reset pending note state when the active project context changes
- cleared the stored note for an item after a successful decision write

### Regression coverage

Files:

- `apps/web/components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx`

Coverage:

- preserved the existing approve flow with default rationale fallback
- added a rejection-path test that submits a custom decision note
- verified that the custom note is sent in the request payload
- verified that queue refresh and execution history refresh still occur after decision writes

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run components/agent/__tests__/AgentOrchestrationWorkspaceClient.test.tsx'`
  - `6 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `77 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `827 passed, 31 skipped, 1 warning`

## Next order

1. Add bulk approval and rejection actions for project-level queues so portfolio reviews do not require item-by-item writes.
2. Add tenant-wide approval audit filters and read views if operations needs a cross-project queue console.
3. Add explicit decision timestamps and rationale history rendering if resolved approvals should stay visible instead of dropping out of the pending queue.
