# Part G frontend live binding update

Date: 2026-03-22
Stage: 20

## Summary

Extended the frontend live binding from the initial dashboard/auction surfaces into the remaining high-value Part G operator views:

- `analytics/investment` now uses live `ai-costs`, `reports`, and `portals` APIs instead of the dead `/analytics/investment` dependency.
- `analytics/esg` now uses live `energy` APIs instead of the dead `/analytics/esg` dependency.
- Both workspaces are project-aware and support either:
  - selecting a live project from `/projects`
  - manually entering a real existing project UUID when FK-backed persistence is required

## Implemented

### Investment operations workspace

Files:

- `apps/web/components/analytics/InvestmentOperationsWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/analytics/investment/page.tsx`

Bound live operations:

- `GET /ai-costs/dashboard`
- `POST /ai-costs/budget`
- `GET /ai-costs/budget-gate/{endpoint}`
- `POST /reports/investor/generate`
- `GET /portals/market-data/{region_code}`
- `POST /portals/post-all`
- `GET /projects?page=1&page_size=20`

Key behavior:

- AI usage/cost visibility with service-level breakdown
- monthly budget gate configuration
- multilingual investor report generation
- regional portal market data inspection
- multi-portal listing publication against real project IDs

### Energy certification workspace

Files:

- `apps/web/components/analytics/EnergyOperationsWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/analytics/esg/page.tsx`

Bound live operations:

- `POST /energy/kepco/calculate`
- `POST /energy/certification`
- `GET /projects?page=1&page_size=20`

Key behavior:

- KEPCO bill estimation
- project-linked energy grade/ZEB estimation
- BEMS saving-rate impact review
- persisted certification flow using real project FK context

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
- `python -m pytest -q`
  - `817 passed, 31 skipped`

## Next order

1. Expand live binding into `portals / investor reports / ai-costs / energy` dedicated dashboard routes if separate operator surfaces are needed beyond analytics.
2. Replace remaining dead `/analytics/iot` dependency or rewire it to actual maintenance/tenant/asset-intelligence APIs.
3. Add frontend smoke coverage for the new workspaces once UI test harnesses are in place.
