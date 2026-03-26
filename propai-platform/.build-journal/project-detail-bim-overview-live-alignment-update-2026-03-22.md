# Project detail BIM and overview live alignment update

Date: 2026-03-22
Stage: 27

## Summary

Finished the next project-detail execution slice by replacing the placeholder `bim` subroute under `/projects/[id]/*` with a project-scoped live workspace, aligning `/projects/[id]` itself with the real backend project detail response, and keeping `cad` intentionally scoped as an editor-only route.

The BIM route now binds directly to the routed project id for IFC quantity generation and Three.js geometry summary review. The project overview route no longer depends on legacy mock summary assumptions and instead renders module coverage from the live project detail payload. The CAD route was normalized as a stable editor entrypoint rather than being presented as a false live module.

## Implemented

### Live project detail BIM workspace

Files:

- `apps/web/components/projects/ProjectBimWorkspaceClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/bim/page.tsx`

Behavior:

- loads project context from `GET /projects/{id}`
- pre-fills area-driven BIM generation input from the live project when available
- submits `POST /bim/generate-ifc`
- loads `GET /bim/threejs/{project_id}` after BIM generation
- renders BIM quantity metrics and geometry type summaries inline

### Project overview alignment with live backend shape

Files:

- `apps/web/components/projects/ProjectSummaryClient.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/page.tsx`

Behavior:

- loads project detail from `GET /projects/{id}`
- renders live project metadata, runtime mode, summary tiles, and module coverage
- marks project subroutes as either `live` or `editor`
- keeps the overview route aligned with currently implemented project modules instead of legacy mock fields

### CAD route normalization

Files:

- `apps/web/app/[locale]/(dashboard)/projects/[id]/cad/page.tsx`

Behavior:

- keeps CAD available as an editor route
- removes broken placeholder copy and normalizes the route as preview-only
- avoids presenting CAD as a falsely live-integrated project module while current CAD dependencies remain unresolved

## Tests added

Files:

- `apps/web/components/projects/__tests__/ProjectBimWorkspaceClient.test.tsx`
- `apps/web/components/projects/__tests__/ProjectSummaryClient.test.tsx`
- `apps/web/app/[locale]/(dashboard)/projects/[id]/__tests__/project-live-subroutes.test.tsx`

Coverage:

- route-level wiring for:
  - `/projects/[id]`
  - `/projects/[id]/bim`
  - `/projects/[id]/cad`
- live BIM quantity generation and geometry summary for the routed project
- live project overview rendering and module coverage state

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `29 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Known validation blockers

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - fails in existing unrelated files:
    - `components/map/ParcelMapWrapper.tsx`
    - `lib/blockchain.ts`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - fails in existing unrelated files:
    - `components/cad/ThreeScene.tsx`
    - `hooks/useRealtime.ts`
    - `lib/blockchain.ts`

## Remaining review

Project detail routes now stabilized:

- `/projects/[id]`
- `/projects/[id]/finance`
- `/projects/[id]/report`
- `/projects/[id]/drone`
- `/projects/[id]/design`
- `/projects/[id]/bim`
- `/projects/[id]/blockchain`

Project detail route still intentionally editor-only:

- `/projects/[id]/cad`

## Next order

1. Clear the remaining web `type-check` blockers in `ParcelMapWrapper.tsx` and `lib/blockchain.ts` so the project detail routes can be validated under a clean frontend compile gate.
2. Clear the remaining web `lint` blockers in `ThreeScene.tsx`, `useRealtime.ts`, and `lib/blockchain.ts`.
3. Revisit whether `/projects/[id]/cad` should remain editor-only or be promoted to a stable live workspace once the current CAD dependency chain is fixed.
