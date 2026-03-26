# Frontend compile and lint gate restoration update

Date: 2026-03-22
Stage: 28

## Summary

Finished the next execution slice by clearing the remaining frontend `type-check` and `lint` blockers that were left behind after the live project-detail route rollout.

This work did not add new product routes. It restored the frontend validation baseline so the live-bound project detail surface can now be verified under clean compile, lint, component smoke, and backend regression gates.

## Implemented

### Parcel map wrapper alignment

Files:

- `apps/web/components/map/ParcelMapWrapper.tsx`

Behavior:

- removes the broken `./ParcelMap` import path
- binds the wrapper to the existing `CadastralMap` component instead
- uses the shared `@propai/ui` skeleton for dynamic loading
- restores strict typing for parcel and status label props

### Blockchain helper hardening

Files:

- `apps/web/lib/blockchain.ts`

Behavior:

- removes the failing `ethers` dependency import from the compile path
- normalizes the browser wallet contract to a minimal EIP-1193-style provider shape
- keeps explicit provider detection for MetaMask-capable browsers
- makes it clear that contract deployment should flow through the live backend blockchain APIs instead of the old client-side helper

### CAD editor preview stabilization

Files:

- `apps/web/components/cad/ThreeScene.tsx`

Behavior:

- removes the unresolved `three` and `OrbitControls` imports from the compile path
- replaces them with a dependency-light animated canvas preview
- preserves the editor-only character of the CAD route
- adds explicit resize and animation cleanup to avoid effect leakage

### Realtime hook typing cleanup

Files:

- `apps/web/hooks/useRealtime.ts`

Behavior:

- removes the remaining `any` usage
- switches the hook to a generic message type
- uses `useEffectEvent` so the message callback is stable without dependency-array lint noise

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `29 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend validation gates are now green for:

- compile/type generation
- lint
- web smoke tests
- backend regression tests

The CAD route remains intentionally editor-only. The blockchain helper is intentionally API-first and should not be treated as a production-ready client-side deployment path.

## Next order

1. Add focused frontend tests for `ThreeScene`, `ParcelMapWrapper`, and `useRealtime` so the newly restored compile/lint paths also have explicit regression coverage.
2. Revisit whether the editor-only CAD route should stay as a lightweight preview or be promoted to a richer live workspace.
3. If client-side wallet operations are still required, replace the legacy deployment helper with a deliberate wallet integration plan instead of reviving the old `ethers`-based shortcut.
