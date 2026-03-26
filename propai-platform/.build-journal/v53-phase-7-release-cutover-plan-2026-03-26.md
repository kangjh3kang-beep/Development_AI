# v53 Phase 7 plan: browser release cutover

Date: 2026-03-26
Stage target: 54
Status: Completed

## Goal

Turn the v53 implementation from feature-complete into release-verifiable by making browser E2E, accessibility, and final cutover paths executable under the live-first application shell.

## Scope

### Browser runtime and config

- stabilize Playwright against the actual Next.js runtime
- remove outdated browser specs that no longer match the live route inventory
- normalize Next.js config usage so E2E boot uses a single config surface
- fix SSR-sensitive auth code paths that still touched `window` during initial render

### Release-cutover flows

- auth -> dashboard
- project -> finance -> report -> design -> BIM
- maintenance -> tenant -> digital twin
- permit -> contract -> e-sign
- agent -> approval operations
- KDX -> feasibility

### Accessibility

- run critical WCAG audit coverage for:
  - login
  - dashboard
  - approval operations
  - project contracts
  - offline fallback
- keep keyboard navigation coverage on the live auth surface

### Quality-gate enforcement

- add Playwright execution to `scripts/test/verify_system.sh`
- keep `vitest`, `type-check`, `lint`, `pytest`, and system verification green

## Exit criteria

- Playwright release suite passes end-to-end
- accessibility audit suite passes on the designated routes
- `verify_system.sh` includes browser E2E and remains green
- v53 roadmap can be marked complete through Phase v53.7
