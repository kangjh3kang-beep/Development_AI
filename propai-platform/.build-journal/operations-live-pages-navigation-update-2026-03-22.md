# Operations live pages and navigation update

Date: 2026-03-22
Stage: 22

## Summary

Built dedicated operator-facing routes for the live operations modules that were previously only accessible through the combined analytics/iot workspace.

## Implemented

### Shared workspace upgrade

File:

- `apps/web/components/analytics/OperationsIntelligenceWorkspaceClient.tsx`

Changes:

- added section-based rendering control for:
  - `maintenance`
  - `tenant`
  - `asset`
- added `showHero` toggle so the same live workspace can be reused in both:
  - combined analytics view
  - dedicated operator module views

### New dedicated pages

Files:

- `apps/web/app/[locale]/(dashboard)/maintenance/page.tsx`
- `apps/web/app/[locale]/(dashboard)/tenant/page.tsx`
- `apps/web/app/[locale]/(dashboard)/digital-twin/page.tsx`

Behavior:

- each page reuses the live operations workspace with focused sections only
- maintenance page exposes predictive maintenance flow
- tenant page exposes feedback and NPS/health flow
- digital twin page exposes asset intelligence flow

### Navigation

File:

- `apps/web/app/[locale]/(dashboard)/layout.tsx`

Changes:

- added sidebar links for:
  - `Maintenance`
  - `Tenant`
  - `Digital Twin`

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
- `python -m pytest -q`
  - `817 passed, 31 skipped`

## Next order

1. Add frontend smoke or E2E coverage for the live workspaces and new dedicated operations pages.
2. Revisit remaining placeholder-only routes and decide whether to bind or retire them.
