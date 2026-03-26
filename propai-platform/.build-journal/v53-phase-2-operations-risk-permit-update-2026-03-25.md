# v53 phase 2 operations, risk, and permit update

Date: 2026-03-25
Stage: 49

## Summary

Completed `Phase v53.2` of the corrected v53 roadmap by closing the shared operational layer for:

- `G159` digital twin status linkage
- `G160` unified AI risk grading
- `G164` permit submission and tracking

This stage added persisted backend read models, live APIs, RBAC coverage, and a control-tower frontend surface centered on the existing `digital-twin` route.

## Implemented backend scope

Added persistence:

- `apps/api/database/models/phase_v53_operations.py`
- `apps/api/database/migrations/versions/017_add_v53_phase2_operations_tables.py`

Added services:

- `apps/api/services/digital_twin_status_service.py`
- `apps/api/services/risk_scoring_engine.py`
- `apps/api/services/seumter_permit_service.py`

Added and extended routers:

- `apps/api/routers/digital_twin.py`
- `apps/api/routers/risk.py`
- `apps/api/routers/permits.py`

Added contracts and RBAC:

- `packages/schemas/models.py`
- `apps/api/auth/rbac.py`
- `apps/api/main.py`

Available live endpoints now include:

- `POST /api/v1/digital-twin/status/snapshot`
- `GET /api/v1/digital-twin/status/{project_id}/latest`
- `POST /api/v1/risk/unified/analyze`
- `GET /api/v1/risk/unified/{project_id}/latest`
- `POST /api/v1/permits/submit`
- `GET /api/v1/permits/{project_id}/latest`
- `GET /api/v1/permits/submissions/{submission_id}/status`

## Implemented frontend scope

Promoted the `digital-twin` workspace into a v53.2 control tower through:

- `apps/web/components/digital-twin/DigitalTwinControlTowerWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/digital-twin/page.tsx`

The route now supports:

- project-aware digital twin snapshots
- unified risk analysis and latest risk read-back
- permit submission and status read-back
- retryable query-error recovery for all read-side dependencies

## Regression coverage

Backend:

- `tests/unit/test_v53_phase2_operations.py`

Frontend:

- `apps/web/components/digital-twin/__tests__/DigitalTwinControlTowerWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/__tests__/operations-live-pages.test.tsx`

## Verification

Executed successfully:

- `bash scripts/test/verify_system.sh`
  - `PASS 59 / FAIL 0 / WARN 0`
- `.venv/bin/python -m pytest -q`
  - `860 passed, 31 skipped, 1 warning`
- `pnpm test:run`
  - `93 passed`
- `npm run type-check`
  - `passed`
- `npm run lint`
  - `passed`

## Result

After this stage:

- `G159` is implemented with persisted digital twin status snapshots and a live operator surface
- `G160` is implemented with a shared seven-dimension risk engine and project read model
- `G164` is implemented with permit submission, readiness, and tracking APIs

The next v53 target after this stage is contract automation and i18n hardening.
