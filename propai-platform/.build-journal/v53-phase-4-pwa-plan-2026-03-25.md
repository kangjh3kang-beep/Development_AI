# v53 Phase 4 PWA Plan

Date: 2026-03-25
Stage target: 51
Scope: `G163` full mobile PWA support

## Verified baseline before execution

- `apps/web/public/manifest.webmanifest` existed, but only as a metadata shell
- `apps/web/public/sw.js` existed, but the app had no runtime registration path
- no app-level install prompt handling was present
- no notification permission or test push baseline existed in the live UI
- no dedicated offline fallback route existed
- quality gates before implementation were green:
  - `bash scripts/test/verify_system.sh`
  - `.venv/bin/python -m pytest -q`
  - `pnpm test:run`
  - `npm run type-check`
  - `npm run lint`

## Implementation objective

Convert the existing manifest-only baseline into a real field-ready PWA layer without breaking the live-first dashboard model.

## Execution plan

### 1. Runtime bootstrap

- add a client PWA runtime provider under `apps/web/lib/providers.tsx`
- register `/sw.js` once per browser session
- surface:
  - service worker readiness
  - waiting update state
  - install prompt availability
  - notification permission state

### 2. Operator surface

- add a dedicated dashboard PWA status card
- expose:
  - install action
  - update apply action
  - notification permission action
  - test notification action
  - offline fallback route link

### 3. Offline and push baseline

- add `/offline` fallback page
- upgrade `public/sw.js` to support:
  - navigation fallback to `/offline`
  - shell asset precache
  - message-based `SKIP_WAITING`
  - message-based local notification dispatch
  - push and notification click handlers

### 4. Manifest hardening

- enrich `manifest.webmanifest` with:
  - `id`
  - `display_override`
  - categories
  - shortcuts for dashboard, projects, inspection, and cost intelligence

### 5. Regression and gate validation

- add component regression for the PWA status card and runtime provider flow
- extend dashboard route-shell coverage for the new PWA card
- extend auxiliary route coverage for `/offline`
- rerun full quality gates after implementation

## Exit criteria

- service worker registers from the live app shell
- install prompt path is reachable when the browser exposes it
- offline fallback route exists and is cache-targeted
- notification permission and local test notification path are reachable
- manifest, frontend tests, frontend compile/lint, backend pytest, and system verification all remain green
