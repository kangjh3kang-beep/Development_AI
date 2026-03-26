# Part G Foundation, Portals, Investor, and Energy Update

Date: 2026-03-22

## Scope Completed

- Added Part G persistence foundation for:
  - `G91 ai cost budgets`
  - `G92 portals`
  - `G93 investor multilingual reports`
  - `G94 KEPCO cache and energy certification`
- Added live APIs for:
  - portal posting and regional market data
  - investor report generation
  - AI budget persistence and budget-gate evaluation
  - KEPCO calculation and energy certification persistence
- Normalized Part G model exports and canonical schema contracts so the new modules load without duplicate SQLAlchemy table registration.

## API Endpoints Added

- `/api/v1/portals/{portal_id}/post`
- `/api/v1/portals/post-all`
- `/api/v1/portals/market-data/{region_code}`
- `/api/v1/reports/investor/generate`
- `/api/v1/ai-costs/budget`
- `/api/v1/energy/kepco/calculate`
- `/api/v1/energy/certification`

## Files Added

- `apps/api/database/models/phase_g_ai_costs.py`
- `apps/api/database/models/phase_g_energy.py`
- `apps/api/database/migrations/versions/007_add_part_g_foundation_tables.py`
- `apps/api/routers/portals.py`
- `apps/api/services/ai_costs_service.py`
- `apps/api/services/energy_service.py`
- `apps/api/services/portals_service.py`
- `apps/api/services/investor_report_service.py`
- `tests/unit/test_part_g_foundation.py`
- `tests/unit/test_part_g_live_modules.py`

## Files Updated

- `apps/api/auth/rbac.py`
- `apps/api/database/models/__init__.py`
- `apps/api/database/models/phase_g_portal.py`
- `apps/api/database/models/phase_g_multilingual.py`
- `apps/api/main.py`
- `apps/api/routers/ai_costs.py`
- `apps/api/routers/energy.py`
- `apps/api/routers/reports.py`
- `packages/schemas/models.py`
- `.build-journal/current-stage.json`

## Verification

- `python -m pytest -q`
  - `805 passed, 31 skipped`

## Next Execution Order

1. Start `G95` live APIs for chatbot, auction intelligence, and contractor network workflows.
2. Add end-to-end smoke coverage across `underwriting -> reports -> portals` and `ai-costs -> energy -> dashboard`.
3. Begin frontend live binding for Part G modules and replace remaining mock-first screens.
