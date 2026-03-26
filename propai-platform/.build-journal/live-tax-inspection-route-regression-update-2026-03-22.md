# Live tax and inspection route regression update

Date: 2026-03-22
Stage: 24

## Summary

Finished the next frontend execution slice by replacing the top-level `tax` and `inspection` placeholders with live API workspaces, adding route-level smoke coverage for the dedicated operations pages, and locking `api-client` live/mock behavior with direct regression tests.

The remaining mock-only `agent` route was removed from the primary dashboard flow and moved into a preview section.

## Implemented

### New live workspaces

Files:

- `apps/web/components/analytics/TaxOperationsWorkspaceClient.tsx`
- `apps/web/components/analytics/InspectionOperationsWorkspaceClient.tsx`

Behavior:

- `TaxOperationsWorkspaceClient`
  - binds to `GET /projects?page=1&page_size=20`
  - submits live requests to `POST /tax/calculate`
  - renders tax amount, rate, taxable base, deductions, and optimization tips
- `InspectionOperationsWorkspaceClient`
  - binds to `GET /projects?page=1&page_size=20`
  - submits live requests to `POST /drone/inspect`
  - renders processed image count, defect count, severity summary, and detected defect list

### Page wiring

Files:

- `apps/web/app/[locale]/(dashboard)/tax/page.tsx`
- `apps/web/app/[locale]/(dashboard)/inspection/page.tsx`

Changes:

- removed mock calculator/checklist dependency from the top-level pages
- replaced both with live workspace entry surfaces
- preserved the existing placeholder hero pattern, but changed status handling to live/mock runtime mode labels

### Navigation review

Files:

- `apps/web/app/[locale]/(dashboard)/layout.tsx`
- `apps/web/app/[locale]/(dashboard)/page.tsx`

Changes:

- removed mock-only `agent` from the primary dashboard navigation
- added a `Preview` section for the `agent` route
- replaced dashboard landing cards that still targeted `sample-project` placeholder routes with live routes:
  - `tax`
  - `auction`
  - `maintenance`
- updated the hero CTA to use the live `auction` route instead of the mock-only `agent` route

## Tests added

Files:

- `apps/web/app/[locale]/(dashboard)/__tests__/operations-live-pages.test.tsx`
- `apps/web/components/analytics/__tests__/TaxOperationsWorkspaceClient.test.tsx`
- `apps/web/components/analytics/__tests__/InspectionOperationsWorkspaceClient.test.tsx`
- `apps/web/lib/__tests__/api-client.test.ts`

Coverage:

- route-level wiring for:
  - `maintenance`
  - `tenant`
  - `digital-twin`
- live tax workspace request/response rendering
- live inspection workspace request/response rendering
- auth banner behavior on `401`
- `api-client` runtime mode, token detection, mock short-circuit, fetch fallback, and error payload propagation

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `15 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Top-level dashboard flow is now live-first for:

- `dashboard`
- `projects`
- `tax`
- `auction`
- `inspection`
- `maintenance`
- `tenant`
- `digital-twin`

Still preview/mock-oriented:

- `agent`
- multiple project subroutes under `/projects/[id]/*`

## Next order

1. Review project detail subroutes and decide which of `finance / report / design / blockchain / drone` should become live workspaces next.
2. If the agent route must return to the main flow, build a dedicated streaming client for `/agents/orchestrate` or `/agents/analyze/ws/{project_id}` first.
3. Expand route-level smoke coverage from dedicated operations pages to the new `tax` and `inspection` top-level pages.
