# v53 cost intelligence foundation update

Date: 2026-03-25
Stage: 48

## Summary

Implemented `Phase v53.1` of the corrected v53 roadmap by closing the shared foundation for:

- `G158` real-time construction material price integration
- `G165` construction-cost escalation based on PPI and index data

This stage adds the missing backend contracts, persistence, APIs, RBAC, and a live frontend workspace for material-price and escalation operations. The implementation stays consistent with the existing system-construction rules:

- live-first but mock-tolerant backend service design
- explicit persistence for read-back and auditability
- retryable read-side UI states on the frontend
- regression coverage across backend contracts and frontend live workspace behavior

## Implemented backend scope

### Persistence and migration

Added cost-intelligence persistence models:

- `apps/api/database/models/material_price_history.py`
- `apps/api/database/models/cost_escalation_snapshot.py`

Added migration:

- `apps/api/database/migrations/versions/016_add_v53_cost_intelligence_tables.py`

The new tables persist:

- tenant/project-scoped material price history snapshots
- escalation scenario outputs and alert metadata

### Services

Added:

- `apps/api/services/kcci_material_price_service.py`
- `apps/api/services/cost_escalation_engine.py`

Service responsibilities:

- deterministic material-price snapshot generation with region and material filters
- material trend and alert summary shaping
- PPI-style escalation analysis using normalized material/labor/overhead shares
- latest escalation read-back for project-level operations pages

### Router and contracts

Added router:

- `apps/api/routers/cost_intelligence.py`

Wired into:

- `apps/api/main.py`

Added schema contracts in:

- `packages/schemas/models.py`

Added RBAC coverage in:

- `apps/api/auth/rbac.py`

Available endpoints:

- `POST /api/v1/cost-intelligence/material-prices/refresh`
- `GET /api/v1/cost-intelligence/material-prices/latest`
- `POST /api/v1/cost-intelligence/escalation/analyze`
- `GET /api/v1/cost-intelligence/escalation/{project_id}/latest`

## Implemented frontend scope

Added live workspace:

- `apps/web/components/analytics/ConstructionCostWorkspaceClient.tsx`

Added route:

- `apps/web/app/[locale]/(dashboard)/analytics/cost/page.tsx`

Updated navigation:

- `apps/web/app/[locale]/(dashboard)/layout.tsx`

The workspace now supports:

- project picker plus manual project UUID fallback
- live material snapshot loading
- live escalation snapshot loading
- material refresh action
- escalation analysis action
- retryable query-error handling for project, material, and escalation reads

## Regression coverage

Backend:

- `tests/unit/test_v53_cost_intelligence.py`

Frontend:

- `apps/web/components/analytics/__tests__/ConstructionCostWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`

## Verification

Executed:

- `wsl -d Ubuntu bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest tests/unit/test_v53_cost_intelligence.py -q'`
  - `8 passed`
- `wsl -d Ubuntu bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run -- ConstructionCostWorkspaceClient dashboard-route-shells'`
  - `30 files passed, 87 tests passed`
- `wsl -d Ubuntu bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl -d Ubuntu bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl -d Ubuntu bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `839 passed, 31 skipped, 1 warning`

## Resulting v53 status

After this stage:

- `G158` is no longer missing; it now has persistence, service logic, routes, RBAC, tests, and a visible operator surface
- `G165` is no longer missing; it now has escalation analysis persistence, routes, tests, and a live workspace

The remaining priority items from the corrected v53 roadmap are now:

1. `Phase v53.2`: `G159`, `G160`, `G164`
2. `Phase v53.3`: `G161` and final `G162` hardening
3. `Phase v53.4`: `G163` PWA completion
4. operator-surface and auth hardening still outside the official delta

## Next implementation target

Proceed to `Phase v53.2` with this order:

1. add a v53 digital-twin status engine that merges BIM, IoT, energy, and anomaly context
2. add a unified risk-scoring engine with shared project and scenario outputs
3. add permit submission and permit-status tracking APIs plus project-facing workspace flows
