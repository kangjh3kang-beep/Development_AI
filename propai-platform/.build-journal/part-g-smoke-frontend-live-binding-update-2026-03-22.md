# Part G Smoke and Frontend Live Binding Update

Date: 2026-03-22

## Scope Completed

- Added cross-module smoke coverage for:
  - `underwriting -> investor reports -> portals`
  - `chatbot -> auction -> contractors`
- Started frontend live binding on the web workspace:
  - dashboard panel now maps to live `system` and `dashboard` endpoints when API access is configured
  - auction route now hosts a live G95 workspace across auction analysis, contractor recommendations, and advisory chatbot
- Added frontend API token support through:
  - `NEXT_PUBLIC_API_ACCESS_TOKEN`
  - `localStorage.propai_access_token`

## Frontend Files Updated

- `apps/web/lib/api-client.ts`
- `apps/web/components/dashboard/DashboardClientPanel.tsx`
- `apps/web/components/auction/AuctionWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/auction/page.tsx`
- `apps/web/app/[locale]/(dashboard)/layout.tsx`
- `.env.example`

## Backend/Test Files Added

- `tests/unit/test_part_g_smoke_chains.py`

## Verification

- `python -m pytest -q`
  - `817 passed, 31 skipped`
- `apps/web`
  - `npm run type-check`
  - `npm run lint`

## Next Execution Order

1. Extend frontend live binding beyond `auction` into `portals`, `investor reports`, `ai-costs`, and `energy` workspace screens.
2. Add authenticated project-scoped live bindings once web login/JWT handling is connected.
3. Re-run `ruff` and `mypy`, then prepare a frontend-backend route inventory for remaining mock-first pages.
