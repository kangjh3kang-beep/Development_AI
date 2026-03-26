# v53.3 contract automation and i18n hardening plan

Date: 2026-03-25
Pre-stage: 49
Status: Active execution plan after full quality-gate recovery

## Quality-gate baseline

Revalidated before planning:

- `bash scripts/test/verify_system.sh`
  - `PASS 58 / FAIL 0 / WARN 0`
- `.venv/bin/python -m pytest -q`
  - `851 passed, 31 skipped, 1 warning`
- `pnpm test:run`
  - `89 passed`
- `npm run type-check`
  - `passed`
- `npm run lint`
  - `passed`

## Goal

Execute `Phase v53.3` from the corrected v53 roadmap:

- `G161` smart contract generation with e-sign support
- `G162` multilingual consistency on newly added v53 surfaces

## Why this execution order

The current codebase already has:

- persisted lease and contractor workflows
- a live `esign` router
- project-scoped live subroutes

What is still missing is the workflow glue:

1. generate a contract draft from project context
2. persist the draft as a read model
3. hand the draft into the existing e-sign path
4. surface the workflow in the localized frontend

So this phase should not add a disconnected e-sign demo. It should add a project-facing contract workflow that uses the existing e-sign infrastructure as the final write step.

## Backend implementation scope

### 1. Contract draft persistence

Add a new persisted model for generated contract drafts.

The read model should keep:

- tenant and project scope
- contract type
- target language
- counterparty
- effective date and contract amount
- generated summary, key terms, clauses, and rendered body
- document URL placeholder
- sign status and linked `esign_request_id`

### 2. Contract generator service

Add `contract_generator.py` with deterministic template generation for:

- sale
- lease
- construction
- consulting

The generator should:

- use project metadata as context
- support `ko`, `en`, and `zh-CN`
- generate clause blocks and key terms instead of a single opaque blob
- return a stable draft that can be reloaded later

### 3. Contract workflow router

Add a contracts router with three core endpoints:

- `POST /api/v1/contracts/generate`
- `GET /api/v1/contracts/{project_id}/latest`
- `POST /api/v1/contracts/{draft_id}/esign`

The e-sign handoff should reuse the existing `ESignRequest` model and create a linked request rather than duplicating a second signing subsystem.

### 4. Cross-cutting backend work

- migration for the new draft table
- schema contracts in `packages/schemas/models.py`
- router wiring in `apps/api/main.py`
- RBAC coverage for `contracts`
- `verify_system.sh` service-import coverage for the new generator service

## Frontend implementation scope

Add a new project-scoped live contract route:

- `/[locale]/projects/[id]/contracts`

The route should provide:

- project-aware draft generation
- language selection across `ko`, `en`, `zh-CN`
- latest draft read-back
- direct e-sign request handoff
- retryable project and draft query states

Also harden `G162` for this surface by:

- adding locale labels to `common.json`
- wiring the new module label into project summary navigation
- ensuring the new contract workspace itself renders localized copy

## Verification scope

Backend:

- schema and router tests for contract draft generation and e-sign handoff
- deterministic template tests across language and contract-type branches
- RBAC coverage for the new `contracts` resource

Frontend:

- component regression for project contract generation and e-sign request
- route-level regression for the new project contracts page
- project overview regression for the added module link

## Exit criteria

This phase is complete when:

- a project contract draft can be generated from a live route
- the latest draft is persisted and reloaded
- the draft can be handed off to the existing e-sign workflow
- the new surface is localized for Korean, English, and Simplified Chinese
- quality gates remain green after integration
