# v53 phase 3 contracts and i18n update

Date: 2026-03-25
Stage: 50

## Summary

Completed `Phase v53.3` of the corrected v53 roadmap by closing:

- `G161` smart contract generation with e-sign support
- the remaining `G162` hardening needed for newly added v53 surfaces

This stage added project-scoped contract draft persistence, deterministic multilingual draft generation, e-sign handoff, and a live project contracts route.

## Implemented backend scope

Added persistence and migration:

- `apps/api/database/models/phase_v53_contracts.py`
- `apps/api/database/migrations/versions/018_add_v53_contract_generation_tables.py`

Added service and router:

- `apps/api/services/contract_generator.py`
- `apps/api/routers/contracts.py`

Updated shared contracts, router wiring, RBAC, and system verification:

- `packages/schemas/models.py`
- `apps/api/main.py`
- `apps/api/auth/rbac.py`
- `scripts/test/verify_system.sh`

Available live endpoints now include:

- `POST /api/v1/contracts/generate`
- `GET /api/v1/contracts/{project_id}/latest`
- `POST /api/v1/contracts/{draft_id}/esign`

The backend now supports:

- sale, lease, construction, and consulting draft generation
- persisted clause and key-term read models
- linked reuse of the existing `ESignRequest` workflow instead of a parallel signing subsystem

## Implemented frontend scope

Added the project-scoped live route:

- `apps/web/app/[locale]/(dashboard)/projects/[id]/contracts/page.tsx`

Added the live workspace:

- `apps/web/components/projects/ProjectContractWorkspaceClient.tsx`

Updated navigation and locale coverage:

- `apps/web/components/projects/ProjectSummaryClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/page.tsx`
- `apps/web/i18n/get-dictionary.ts`
- `apps/web/public/locales/en/common.json`
- `apps/web/public/locales/ko/common.json`
- `apps/web/public/locales/zh-CN/common.json`

The route now supports:

- project-aware contract draft generation
- latest persisted draft reload
- direct e-sign handoff
- Korean, English, and Simplified Chinese surface copy
- retryable read-side recovery for project and draft queries

## Regression coverage

Backend:

- `tests/unit/test_v53_phase3_contracts.py`

Frontend:

- `apps/web/components/projects/__tests__/ProjectContractWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectSummaryClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/__tests__/project-live-subroutes.test.tsx`

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

- `G161` is implemented as an actual workflow, not just an existing e-sign endpoint
- `G162` stays green for the new v53 contract surface across `ko`, `en`, and `zh-CN`

The next official v53 priority is `Phase v53.4`, namely full mobile PWA completion for `G163`.
