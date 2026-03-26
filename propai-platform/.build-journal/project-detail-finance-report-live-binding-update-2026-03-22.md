# Project detail finance and report live binding update

Date: 2026-03-22
Stage: 25

## Summary

Finished the next project-detail execution slice by replacing the placeholder `finance` and `report` subroutes under `/projects/[id]/*` with live workspace clients that bind directly to the existing backend APIs.

The finance route now chains persisted AVM valuation and jeonse risk analysis for the routed project id. The report route now generates multilingual investor reports for the routed project id and keeps the returned variants on-screen for review.

## Implemented

### Live project detail finance workspace

Files:

- `apps/web/components/projects/ProjectFinanceWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/finance/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- pre-fills address and area from the live project when available
- submits `POST /avm`
- immediately chains `POST /finance/jeonse-risk` using the AVM estimate as the sale price
- renders persisted AVM metrics and jeonse risk output on the same page

### Live project detail report workspace

Files:

- `apps/web/components/projects/ProjectReportWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/report/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- submits `POST /reports/investor/generate` using the routed project id
- supports operator-controlled project name, asset type, target languages, highlights, risks, and sections
- renders generated multilingual report variants and generated sections inline

### Tests added

Files:

- `apps/web/components/projects/__tests__/ProjectFinanceWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectReportWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/__tests__/project-live-subroutes.test.tsx`

Coverage:

- route-level wiring for:
  - `/projects/[id]/finance`
  - `/projects/[id]/report`
- live AVM plus jeonse-risk chaining for the project finance workspace
- live investor report generation for the project report workspace

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `19 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Known validation blockers

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - fails in existing unrelated files:
    - `components/cad/ThreeScene.tsx`
    - `components/map/ParcelMapWrapper.tsx`
    - `lib/blockchain.ts`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - fails in existing unrelated files:
    - `hooks/useRealtime.ts`
    - `lib/blockchain.ts`

## Remaining review

Project detail routes now live-bound:

- `/projects/[id]/finance`
- `/projects/[id]/report`

Still placeholder or preview-oriented under `/projects/[id]/*`:

- `design`
- `drone`
- `blockchain`

## Next order

1. Replace `/projects/[id]/drone` with a project-scoped live inspection workspace or a thin wrapper around the existing inspection flow.
2. Replace `/projects/[id]/design` with a live design/BIM request surface for `design/floor-plan`, `design/bim/analyze`, or both.
3. Replace `/projects/[id]/blockchain` only after deciding whether the route should expose the full escrow lifecycle or a narrower contract status workspace.
