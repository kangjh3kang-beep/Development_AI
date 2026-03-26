# v53 Phase 6 plan: approval operations center

Date: 2026-03-26
Stage target: 53
Status: Completed

## Goal

Promote domain-agent approvals into a first-class operational workflow that can be used independently of the agent execution surface.

## Scope

### Backend

- extend `/api/v1/agents/domain/approvals` with `approver_role` filtering
- keep existing history and approval contracts stable for the agent workspace
- preserve project-scoped batch decision policy and do not enable tenant-wide bulk actions

### Frontend

- add a dedicated `/${locale}/approvals` route
- add navigation and dashboard-home entry points for approval operations
- split queue, history, summary, and decision actions into a focused approval-operations workspace
- support tenant-wide audit mode with `scope`, `status`, `approver role`, and `limit` filters

### Verification

- backend regression for approval queue filtering
- workspace regression for project-scoped bulk action flow
- workspace regression for tenant-wide audit and approver-role filtering
- dashboard route-shell and home-navigation regression updates
- full quality gates:
  - `pnpm test:run`
  - `npm run type-check`
  - `npm run lint`
  - `.venv/bin/python -m pytest -q`
  - `bash scripts/test/verify_system.sh`

## Exit criteria

- approval review is usable from a dedicated live route
- tenant-wide and project-scoped audit filters are available without regressing the existing agent workspace
- project-level batch approval remains constrained to project scope
- full quality gates pass after the approval-operations changes
