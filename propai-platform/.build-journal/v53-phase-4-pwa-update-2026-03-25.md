# v53 Phase 4 PWA Update

Date: 2026-03-25
Stage: 51
Scope: `G163` full mobile PWA support

## Implemented

### Runtime bootstrap

- added `apps/web/components/pwa/PwaRuntimeProvider.tsx`
- mounted the provider in `apps/web/lib/providers.tsx`
- runtime now tracks:
  - service worker registration state
  - cached update readiness
  - install prompt availability
  - notification permission state
  - local test-notification dispatch

### Dashboard operator surface

- added `apps/web/components/pwa/PwaStatusCard.tsx`
- mounted the card in `apps/web/app/[locale]/(dashboard)/page.tsx`
- the live dashboard now exposes:
  - install workspace action
  - refresh/apply PWA action
  - notification enable action
  - test notification action
  - offline fallback entry

### Offline and push baseline

- added `apps/web/app/offline/page.tsx`
- upgraded `apps/web/public/sw.js` with:
  - shell precache
  - offline navigation fallback
  - API network-first fallback
  - `SKIP_WAITING` message handling
  - local notification message handling
  - push and notification click handlers

### Manifest and i18n

- upgraded `apps/web/public/manifest.webmanifest` with `id`, `display_override`, categories, and shortcuts
- extended `apps/web/i18n/get-dictionary.ts`
- added localized PWA copy in:
  - `apps/web/public/locales/en/common.json`
  - `apps/web/public/locales/ko/common.json`
  - `apps/web/public/locales/zh-CN/common.json`

### Regression coverage

- added `apps/web/components/pwa/__tests__/PwaStatusCard.test.tsx`
- extended:
  - `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-home-navigation.test.tsx`
  - `apps/web/app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx`
  - `apps/web/app/__tests__/auxiliary-route-shells.test.tsx`
  - `apps/web/test/setup.ts`
  - `apps/web/vitest.config.ts`

## Quality gates

- `pnpm test:run` -> `96 passed`
- `npm run type-check` -> passed
- `npm run lint` -> passed
- `.venv/bin/python -m pytest -q` -> `860 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 59 / FAIL 0 / WARN 0`

## Result

`G163` is now implemented as a real install/offline/push-ready browser runtime rather than a manifest-only placeholder.

## Next recommended phase

Move to `v53.5`:

- replace `safety`, `webrtc`, and `sre` placeholder shells with explicit live workspaces
- harden auth lifecycle with refresh, expiry recovery, logout, and Kakao callback completion
