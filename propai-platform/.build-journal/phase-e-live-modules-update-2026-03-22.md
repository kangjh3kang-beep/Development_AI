# Phase E Live Modules Update

Date: 2026-03-22

## Scope Completed

- Added live APIs for:
  - `G82 compliance`
  - `G83 leases / IFRS16`
  - `G84 esg / GRESB`
- Reused the existing Phase E tables and extended shared request/response contracts.
- Added deterministic scoring logic for AML risk, IFRS16 lease schedules, and ESG/GRESB assessment.

## API Endpoints Added

- `/api/v1/compliance/screening`
- `/api/v1/leases/analyze`
- `/api/v1/esg/assessment`

## Files Added

- `apps/api/services/compliance_service.py`
- `apps/api/services/lease_service.py`
- `apps/api/services/esg_service.py`
- `apps/api/routers/compliance.py`
- `apps/api/routers/leases.py`
- `apps/api/routers/esg.py`
- `tests/unit/test_phase_e_live_modules.py`

## Files Updated

- `apps/api/main.py`
- `packages/schemas/models.py`
- `.build-journal/current-stage.json`

## Verification

- `python -m pytest -q`
  - `759 passed, 34 skipped`

## Next Execution Order

1. Start Part F live APIs: marketing / OM, domain agents, maintenance, tenant experience, asset intelligence.
2. Bind the new Phase E modules into dashboard and project-level frontend flows.
3. Add smoke tests that chain `underwriting -> compliance -> leases -> esg -> climate` for a single sample project.
