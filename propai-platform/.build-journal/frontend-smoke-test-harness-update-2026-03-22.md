# Frontend smoke test harness update

Date: 2026-03-22
Stage: 23

## Summary

Added a frontend smoke-test harness for the new live workspaces so the post-v43 dashboard bindings are no longer protected only by lint and manual checks.

## Implemented

### Vitest harness

Files:

- `apps/web/package.json`
- `apps/web/vitest.config.ts`
- `apps/web/test/setup.ts`
- `apps/web/test/render-with-query-client.tsx`

Changes:

- added `vitest`-based test scripts:
  - `test`
  - `test:run`
- added `jsdom` and Testing Library dependencies for component-level smoke coverage
- added a shared React Query render helper for live workspace tests
- configured `jsdom`, alias resolution, and test setup stubs in Vitest

### Live workspace smoke coverage

Files:

- `apps/web/components/analytics/__tests__/InvestmentOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/EnergyOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/OperationsIntelligenceWorkspaceClient.test.tsx`

Covered flows:

- investment operations workspace:
  - live project loading
  - AI cost dashboard rendering
  - portal market snapshot rendering
  - budget save action
- energy operations workspace:
  - live project loading
  - energy certification request
  - certification result and recommendation rendering
- operations intelligence workspace:
  - section-scoped rendering for dedicated pages
  - asset intelligence execution path

### Backend verification dependency fix

File:

- `apps/api/pyproject.toml`

Changes:

- added `xmltodict` to API dependencies so the XML parsing path exercised by backend tests is part of the declared environment

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `4 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Next order

1. Extend frontend smoke coverage from component level to route-level flows for the dedicated `maintenance`, `tenant`, and `digital-twin` pages.
2. Add a small live-mode regression suite for token-gated API client behavior and error banners.
3. Review the remaining dashboard routes for placeholder-only content and either bind or retire them.
