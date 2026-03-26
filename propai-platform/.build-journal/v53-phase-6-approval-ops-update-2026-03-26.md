# v53 Phase 6 update: approval operations center

Date: 2026-03-26
Stage: 53
Status: Completed

## Delivered

### Backend

- Extended `/api/v1/agents/domain/approvals` to support `approver_role` filtering
- Preserved compatibility for the existing agent-workspace history and approval contracts
- Added backend regression coverage for approval-queue role filtering in `tests/unit/test_v53_phase6_approval_ops.py`

### Frontend

- Added dedicated approval-operations route:
  - `apps/web/app/[locale]/(dashboard)/approvals/page.tsx`
- Added a focused live workspace:
  - `apps/web/components/agent/ApprovalOperationsWorkspaceClient.tsx`
- Promoted approval operations into dashboard navigation and dashboard-home overview cards
- Added tenant-wide audit mode with:
  - scope filter
  - status filter
  - approver-role filter
  - record-limit filter
- Kept batch approve/reject constrained to project scope while allowing resolved-history review across the tenant
- Added locale navigation labels for the new approval route in `en`, `ko`, and `zh-CN`

### Regression coverage

- Added component regression coverage in `apps/web/components/agent/__tests__/ApprovalOperationsWorkspaceClient.test.tsx`
- Extended dashboard route-shell coverage in `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`
- Extended dashboard home navigation coverage in `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`
- Added backend regression coverage in `tests/unit/test_v53_phase6_approval_ops.py`

## Quality gates

- `pnpm test:run` -> `106 passed`
- `npm run type-check` -> `passed`
- `npm run lint` -> `passed`
- `.venv/bin/python -m pytest -q` -> `868 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 59 / FAIL 0 / WARN 0`

## Next phase

`Phase v53.7`: browser E2E, accessibility execution, and final release cutover.
