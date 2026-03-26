# v53 Phase 5 plan: operator shells and auth lifecycle hardening

Date: 2026-03-26
Stage target: 52
Status: Completed

## Goal

Close the main release-trust gaps left after the official v53 delta by:

- removing placeholder-first route shells for `safety`, `webrtc`, and `sre`
- completing the auth lifecycle with refresh, expiry recovery, logout, and Kakao callback handling
- keeping read-side retry and regression coverage consistent

## Scope

### Backend

- add read endpoints for:
  - `/api/v1/safety/dashboard`
  - `/api/v1/parking/dashboard`
  - `/api/v1/webrtc/transcripts`
  - `/api/v1/webrtc/sessions/active`
  - `/api/v1/sre/dashboard`
- add `/api/v1/auth/logout`
- extend RBAC for `safety`, `parking`, `webrtc`, and `sre`

### Frontend

- replace placeholder shells in:
  - `apps/web/app/[locale]/(dashboard)/safety/page.tsx`
  - `apps/web/app/[locale]/(dashboard)/webrtc/page.tsx`
  - `apps/web/app/[locale]/(dashboard)/sre/page.tsx`
- harden `AuthWorkspaceClient` for:
  - refresh-token driven recovery
  - browser session restoration
  - logout flow
- add live Kakao callback completion route and workspace

### Verification

- dashboard route-shell smoke for `safety`, `webrtc`, and `sre`
- auth workspace and Kakao callback component tests
- backend regression test for operator/auth contracts
- full quality gates:
  - `pnpm test:run`
  - `npm run type-check`
  - `npm run lint`
  - `.venv/bin/python -m pytest -q`
  - `bash scripts/test/verify_system.sh`

## Exit criteria

- no primary operator route still presents as a placeholder shell
- auth supports login, register, restore, refresh, Kakao callback, and logout
- full quality gates pass after the changes
