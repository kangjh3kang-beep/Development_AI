# Frontend regression coverage extension update

Date: 2026-03-22
Stage: 29

## Summary

Finished the next execution slice by adding focused frontend regression tests for the three areas that were stabilized in the previous stage:

- the dependency-light CAD canvas preview
- the dynamic cadastral map wrapper
- the typed realtime websocket hook

This closes the gap between compile/lint restoration and automated regression coverage. The repaired frontend paths are now verified by tests instead of relying only on static gates.

## Implemented

### CAD preview tests

Files:

- `apps/web/components/cad/__tests__/ThreeScene.test.tsx`

Coverage:

- canvas preview bootstraps and clears the loading overlay
- animation frame and resize listeners are cleaned up on unmount
- the component falls back to an explicit error state when no canvas context is available

### Cadastral map wrapper test

Files:

- `apps/web/components/map/__tests__/ParcelMapWrapper.test.tsx`

Coverage:

- the wrapper still binds through `next/dynamic`
- the dynamic loader keeps the expected skeleton shape
- typed parcel and label props are forwarded through the wrapper contract

### Realtime hook test

Files:

- `apps/web/hooks/__tests__/useRealtime.test.tsx`

Coverage:

- the websocket is opened against the expected channel path
- callback updates are honored without reopening the socket for the same channel
- sockets are closed when the channel changes and when the hook unmounts

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && pnpm --filter @propai/web test:run'`
  - `33 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `817 passed, 31 skipped`

## Remaining review

Frontend gates are now green across:

- type-check
- lint
- project-detail live route smoke coverage
- frontend component regression coverage for CAD preview, map wrapper, and realtime hook

The CAD route remains intentionally editor-only, and the blockchain helper remains intentionally API-first.

## Next order

1. Add route-level smoke coverage for any remaining editor-only or preview-only dashboard pages that still depend on thin wrappers.
2. Revisit the CAD route once there is a deliberate decision to either keep the lightweight preview or restore a richer editor runtime.
3. If realtime UX expands beyond raw websocket events, add integration-level UI tests for the components that consume `useRealtime`.
