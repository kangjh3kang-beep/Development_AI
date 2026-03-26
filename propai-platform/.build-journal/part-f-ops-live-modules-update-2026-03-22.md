# Part F Ops Live Modules Update

Date: 2026-03-22

## Scope Completed

- Added live APIs for:
  - `G88 maintenance`
  - `G89 tenant experience`
  - `G90 asset intelligence`
- Added deterministic services for:
  - anomaly scoring, RUL, HVAC efficiency, and work-order generation
  - tenant sentiment, AI reply, NPS, and tenant financial health
  - digital-twin asset intelligence with maintenance / tenant / climate / AVM signal aggregation

## API Endpoints Added

- `/api/v1/maintenance/detect-anomaly`
- `/api/v1/tenant/feedback/analyze`
- `/api/v1/tenant/satisfaction/nps`
- `/api/v1/digital-twin/asset-intelligence`

## Files Added

- `apps/api/services/maintenance_service.py`
- `apps/api/services/tenant_experience_service.py`
- `apps/api/services/asset_intelligence_service.py`
- `apps/api/routers/maintenance.py`
- `apps/api/routers/tenant.py`
- `apps/api/routers/digital_twin.py`
- `tests/unit/test_part_f_ops_live_modules.py`

## Files Updated

- `apps/api/main.py`
- `packages/schemas/models.py`
- `.build-journal/current-stage.json`

## Verification

- `python -m pytest -q`
  - `791 passed, 31 skipped`

## Next Execution Order

1. Start Part G foundations and live APIs for portals, investor reports, KEPCO, and energy certification.
2. Add chained smoke tests across `maintenance -> tenant -> digital-twin` and `underwriting -> compliance -> leases -> esg -> climate`.
3. Begin frontend live binding for the new Part F operational modules.
