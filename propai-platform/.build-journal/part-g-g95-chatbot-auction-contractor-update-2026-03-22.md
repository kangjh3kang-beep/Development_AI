# Part G G95 Chatbot, Auction, and Contractor Update

Date: 2026-03-22

## Scope Completed

- Added live APIs for:
  - `G95 chatbot`
  - `G95 auction intelligence`
  - `G95 contractor network`
- Normalized the supporting ORM and migration definitions for:
  - `chatbot_sessions`
  - `chatbot_messages`
  - `auction_listings`
  - `contractors`
- Extended canonical schema contracts and RBAC to cover the full G95 surface.

## API Endpoints Added

- `/api/v1/chatbot/sessions`
- `/api/v1/chatbot/messages`
- `/api/v1/auction/analyze`
- `/api/v1/auction/opportunities`
- `/api/v1/contractors/register`
- `/api/v1/contractors/recommend`

## Files Added

- `apps/api/services/chatbot_service.py`
- `apps/api/services/auction_service.py`
- `apps/api/services/contractor_service.py`
- `apps/api/routers/chatbot.py`
- `apps/api/routers/auction.py`
- `apps/api/routers/contractors.py`
- `tests/unit/test_part_g_g95_live_modules.py`

## Files Updated

- `apps/api/database/models/phase_g_chatbot.py`
- `apps/api/database/models/phase_g_operations.py`
- `apps/api/database/models/__init__.py`
- `apps/api/database/migrations/versions/008_add_chatbot_auction_contractor_tables.py`
- `apps/api/auth/rbac.py`
- `apps/api/main.py`
- `packages/schemas/models.py`
- `.build-journal/current-stage.json`

## Verification

- `python -m pytest -q`
  - `815 passed, 31 skipped`

## Next Execution Order

1. Add Part G end-to-end smoke coverage across `underwriting -> reports -> portals` and `chatbot -> auction -> contractors`.
2. Start frontend live binding for the remaining Part G screens and replace mock-first data paths.
3. Re-run `ruff` and `mypy`, then prepare an integration readiness pass for DB migrations and route inventory.
