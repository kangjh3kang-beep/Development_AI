# Implementation status and gap analysis update

Date: 2026-03-23
Stage: 46

## Summary

Re-audited the current PropAI implementation after stage 45, verified the active quality gates again, and closed the largest remaining product-level placeholder gap: authentication.

The backend already covered most of the v43 live operational surface across Part E, Part F, Part G, KDX, feasibility, and domain-agent approval operations. The most visible missing user-facing path was still login and registration. This stage converts authentication from placeholder pages into a live workflow and records the next remaining gaps in a prioritized execution plan.

## Verified current implementation

### Backend

- v43-aligned live API surface is present across:
  - core system and dashboard
  - underwriting, climate, compliance, leases, ESG
  - marketing, domain agents, maintenance, tenant experience, digital twin
  - portals, investor reports, AI costs, energy, chatbot, auction, contractors
  - KDX live overview and feasibility persistence
- domain-agent approval operations now include:
  - execution history reads
  - approval queue reads
  - single-item approval decisions
  - project-level bulk decisions
  - tenant-wide audit filters and cross-project read views
- authentication is now live for:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/refresh`
  - `GET /api/v1/auth/me`

### Frontend

- dashboard landing, analytics pages, project subroutes, KDX, feasibility, and agent orchestration are already bound to live backend paths
- login and registration are no longer placeholder cards
- the new auth workspace now:
  - submits live login and registration requests
  - stores access and refresh tokens in browser storage
  - revalidates the session through `/auth/me`
  - renders current user, tenant, role, token expiry, and session source
  - lets operators clear the browser session or jump directly to the dashboard

### Quality and verification

- backend router and contract checks passed after the auth changes
- frontend component and route-shell regressions passed after the auth changes
- `vitest` is now scoped to app/component/unit tests only and no longer attempts to execute Playwright e2e specs
- Playwright typing dependencies were added so `npm run type-check` can include the `e2e/` tree without failing on missing modules

## Implemented in stage 46

### Backend auth registration path

Files:

- `apps/api/routers/auth.py`
- `apps/api/tests/test_router_auth.py`
- `tests/unit/test_auth_register_contracts.py`

Changes:

- added `RegisterRequest`
- added tenant slug normalization and uniqueness helpers
- added `POST /api/v1/auth/register`
- registration now creates:
  - a new tenant
  - the first admin user for that tenant
  - an access token and refresh token pair
- added validation and contract coverage for the new path

### Frontend live auth workspace

Files:

- `apps/web/components/auth/AuthWorkspaceClient.tsx`
- `apps/web/components/auth/__tests__/AuthWorkspaceClient.test.tsx`
- `apps/web/app/[locale]/(auth)/login/page.tsx`
- `apps/web/app/[locale]/(auth)/register/page.tsx`
- `apps/web/app/[locale]/(auth)/__tests__/auth-route-shells.test.tsx`

Changes:

- replaced login/register placeholders with a shared live auth client
- added mode switching between login and registration
- added browser token persistence and session clear actions
- added `/auth/me` revalidation after auth success and on stored-session restore
- added route-shell coverage for both auth routes

### Frontend test-gate normalization

Files:

- `apps/web/vitest.config.ts`
- `apps/web/package.json`
- `pnpm-lock.yaml`

Changes:

- limited `vitest` discovery to project test files instead of third-party or e2e specs
- added `@playwright/test`
- added `@axe-core/playwright`
- restored `type-check` compatibility with the existing Playwright e2e tree

## Remaining gaps

### 1. Operations route-shell quality is still inconsistent

- `safety`, `sre`, and `webrtc` have live routers and frontend components, but page-level copy and shell quality are inconsistent
- the route headers still depend on brittle placeholder shells rather than purpose-built live workspaces
- this is now the largest visible UX gap after auth

### 2. Authentication is live but not yet hardened

- no password reset flow
- no logout-all-devices or refresh-token management UI
- no frontend Kakao OAuth callback completion flow
- no session expiry warning or silent refresh UX

### 3. Domain-agent approval operations still need a dedicated operations surface

- tenant-wide audit works inside the embedded workspace
- there is no dedicated cross-project approval operations page yet
- resolved approval rationale presentation can be improved further
- approver-role segmentation is still missing

### 4. CAD remains intentionally limited

- project summary still marks CAD as editor-only
- the route is intentionally separated until the editor dependency path is fully normalized
- this is a known technical constraint, not an accidental regression

### 5. Playwright runtime execution is still unverified in this stage

- Playwright typing and package dependencies now exist
- actual browser E2E execution was not run in this turn
- CI wiring and local runtime verification remain pending

## Detailed next implementation plan

### Phase 46.1: Operations shell normalization

Goal:
replace mixed placeholder/live shells on `safety`, `webrtc`, and `sre` with explicit live workspace pages

Execution:

1. introduce dedicated workspace clients for safety, parking, webrtc, and SRE
2. remove `ModulePlaceholder` dependency from those routes
3. attach retryable query-error states to each live read model
4. add route-shell and component regressions for each operations page

Exit criteria:

- all operations pages render live-specific copy and controls
- no user-facing placeholder shell remains on those routes
- vitest and type-check remain green

### Phase 46.2: Auth hardening

Goal:
move auth from live-and-usable to operationally robust

Execution:

1. add refresh-token reissue path in the browser client
2. add session-expiry warning and recovery UI
3. add Kakao callback frontend handoff
4. add logout and browser-session invalidation coverage

Exit criteria:

- login, register, restore, refresh, and logout paths are all covered
- auth failures are surfaced as actionable UI states

### Phase 46.3: Dedicated approval operations page

Goal:
split tenant-wide approval review from the embedded agent workspace into a first-class operations surface

Execution:

1. add a route-level approval operations page
2. add approver-role and status filters
3. surface resolved rationale and decision timestamps more prominently
4. preserve single-item and bulk project actions where allowed

Exit criteria:

- cross-project approval review no longer depends on running an analysis page first
- queue operations remain synchronized with execution history

### Phase 46.4: Playwright execution baseline

Goal:
turn the newly typed e2e tree into an executable browser regression layer

Execution:

1. verify Playwright browser installation
2. run the existing `e2e/` suite locally or in CI
3. fix any route assumptions introduced by live bindings
4. separate component-test and e2e-test scripts explicitly if needed

Exit criteria:

- e2e specs run without dependency failures
- browser regression becomes a reliable release gate

## Verification

- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q apps/api/tests/test_router_auth.py tests/unit/test_auth_register_contracts.py'`
  - `12 passed, 2 warnings`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && pnpm test:run'`
  - `84 passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run type-check'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/web && npm run lint'`
  - `passed`
- `wsl bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI/propai-platform && .venv/bin/python -m pytest -q'`
  - `831 passed, 31 skipped, 1 warning`
