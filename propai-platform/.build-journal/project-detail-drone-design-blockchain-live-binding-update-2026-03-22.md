# Project detail drone, design, and blockchain live binding update

Date: 2026-03-22
Stage: 26

## Summary

Finished the next project-detail execution slice by replacing the remaining placeholder `drone`, `design`, and `blockchain` subroutes under `/projects/[id]/*` with live workspace clients.

The drone route now runs persisted inspection against the routed project id. The design route now drives floor-plan generation plus auto-IFC and carbon analysis from the routed project id. The blockchain route now exposes a narrower escrow workspace for next-id lookup, escrow creation, and on-chain status review.

## Implemented

### Live project detail drone workspace

Files:

- `apps/web/components/projects/ProjectDroneWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/drone/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- submits `POST /drone/inspect`
- renders persisted image count, defect count, severity summary, and detected defect list

### Live project detail design workspace

Files:

- `apps/web/components/projects/ProjectDesignWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/design/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- submits `POST /design/floor-plan`
- submits `POST /bim/generate-ifc`
- chains `POST /bim/carbon` from generated material breakdown
- renders floor-plan output, BIM quantities, and carbon reduction tips inline

### Live project detail blockchain workspace

Files:

- `apps/web/components/projects/ProjectBlockchainWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/blockchain/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- reads `GET /blockchain/escrow/next-id`
- creates `POST /blockchain/escrow`
- supports `GET /blockchain/escrow/{id}` lookup for on-chain status review
- intentionally keeps the project route scoped to a narrower escrow workspace instead of the full lifecycle

## Tests added

Files:

- `apps/web/components/projects/__tests__/ProjectDroneWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectDesignWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectBlockchainWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/__tests__/project-live-subroutes.test.tsx`

Coverage:

- route-level wiring for:
  - `/projects/[id]/drone`
  - `/projects/[id]/design`
  - `/projects/[id]/blockchain`
- live drone inspection for the routed project
- live floor-plan plus auto-IFC plus carbon chaining
- live escrow create plus status lookup flow

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `25 passed`
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
- `/projects/[id]/drone`
- `/projects/[id]/design`
- `/projects/[id]/blockchain`

Still review-heavy or placeholder-oriented under `/projects/[id]/*`:

- `bim`
- `cad`

## Next order

1. Replace `/projects/[id]/bim` with a project-scoped live viewer/quantity route around `bim/threejs`, `bim/generate-ifc`, or both.
2. Decide whether `/projects/[id]/cad` should stay as an editor-only route or be refit to a stable live parametric workspace once the current CAD type-check blockers are resolved.
3. Revisit project summary routing so `/projects/{id}` itself is aligned with the live backend project detail shape instead of legacy mock expectations.
