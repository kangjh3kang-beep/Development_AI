# v53.2 operations, risk, and permit execution plan

Date: 2026-03-25
Pre-stage: 48
Status: Active execution plan after quality-gate pass

## Quality-gate baseline

The implementation baseline was revalidated before planning:

- `bash scripts/test/verify_system.sh`
  - `PASS 55 / FAIL 0 / WARN 0`
- `.venv/bin/python -m pytest -q`
  - `839 passed, 31 skipped, 1 warning`
- `pnpm test:run`
  - `87 passed`
- `npm run type-check`
  - `passed`
- `npm run lint`
  - `passed`

The quality-gate recovery work included:

- installing the missing `arq` runtime into `.venv`
- hardening `scripts/test/verify_system.sh` so it prefers `.venv/bin/python` directly instead of relying on shell `PATH`

## Goal

Execute `Phase v53.2` from the corrected v53 roadmap:

- `G159` basic real-time digital twin linkage
- `G160` automated AI risk grading
- `G164` automated permit submission integration

## Why this execution order

The three items are coupled:

1. digital twin status provides operational inputs
2. unified risk scoring consumes those operational and regulatory signals
3. permit readiness closes the decision loop and should surface in the same operator workflow

Implementing them separately would create disconnected APIs and duplicate project pickers on the frontend. So this stage uses a single control-tower pattern.

## Backend implementation scope

### 1. Digital twin status persistence and service

Add a new persisted snapshot model for v53 digital twin status.

Target behavior:

- combine project metadata, energy intensity, sensor health, occupancy, and anomaly context
- calculate EUI using the existing digital-twin utility logic
- derive an operational readiness summary and recommendations
- persist the latest snapshot for project read-back

Planned API surface:

- `POST /api/v1/digital-twin/status/snapshot`
- `GET /api/v1/digital-twin/status/{project_id}/latest`

### 2. Unified risk engine persistence and service

Add a shared risk engine that normalizes seven risk dimensions into a single score.

Risk dimensions:

- market
- financial
- regulatory
- operational
- climate
- construction
- leasing

Target behavior:

- accept scenario inputs from the operator
- optionally incorporate the latest digital twin and permit context
- produce:
  - dimension scores
  - weighted composite score
  - grade
  - downside metrics including `VaR 95` and `P90`
- persist the latest project assessment

Planned API surface:

- `POST /api/v1/risk/unified/analyze`
- `GET /api/v1/risk/unified/{project_id}/latest`

### 3. Permit submission and tracking persistence and service

Add a persistent permit workflow that upgrades the existing checklist generator into a submit-and-track path.

Target behavior:

- reuse `PermitPackageService` checklist and completeness logic
- create a stable permit reference
- persist submission metadata, completeness, readiness, and stage
- expose latest project-level permit status
- expose submission-level tracking read model

Planned API surface:

- `POST /api/v1/permits/submit`
- `GET /api/v1/permits/{project_id}/latest`
- `GET /api/v1/permits/submissions/{submission_id}/status`

### 4. Cross-cutting backend work

- migration for the new persistence tables
- schema contracts in `packages/schemas/models.py`
- router wiring in `apps/api/main.py`
- RBAC entries for:
  - `digital_twin_status`
  - `risk_engine`
  - `permits`

## Frontend implementation scope

Promote the existing `digital-twin` dashboard route into a v53.2 control tower.

Planned surface:

- a new live workspace component that shares one project picker across:
  - digital twin status snapshot
  - unified risk scoring
  - permit submission and tracking
- retryable query-error cards for:
  - project picker
  - latest status snapshot
  - latest risk assessment
  - latest permit submission
- direct write actions for:
  - snapshot refresh
  - risk analysis
  - permit submission

The existing anomaly dashboard can remain as a supporting visualization, but the placeholder shell should be removed from the route.

## Verification scope

Backend:

- contract and router coverage for the new v53.2 endpoints
- deterministic unit tests for:
  - digital twin readiness math
  - risk dimension weighting and downside metrics
  - permit completeness and tracking logic

Frontend:

- component regression for the new control-tower workspace
- route-level regression for the `digital-twin` page after shell replacement

## Exit criteria

This stage is complete when:

- digital twin status has a real persisted read model and live route
- unified risk has a real persisted read model and live route
- permit submission/tracking has a real persisted read model and live route
- the `digital-twin` dashboard route no longer depends on `ModulePlaceholder`
- backend and frontend quality gates remain green
